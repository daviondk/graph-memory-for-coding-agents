"""Frozen-weight topology intervention; split scores computed from same batched node tensors."""
from dataclasses import replace
from pathlib import Path
from collections import defaultdict
import os,sys,time,torch
HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE.parent))
from setup_graph import ROOT,TR,RUN,R18,load,put,pilot
from data import split
from fit_graph import materialize,model_cfg,build_model_from_config
from infer_graph import load_rgcn_checkpoint,build_evidence_dataloader,move_training_batch,split_batch_node_scores
def rank():
    from train import pin
    from graph_memory.retrieval.results import RankedNodeRecord
    from project import CACHE,reqs
    pin();device=os.environ.get('ISE_TOPOLOGY_DEVICE','cuda');torch.set_num_threads(8 if device=='cpu' else 3);start=time.monotonic();base=load(ROOT/'forecast-seal.json')
    assert all(pilot.sha(ROOT/f)==v for f,v in base['forecasts'].items())
    att=load(HERE/'edge-invariants.json');assert att['transformed_sha']==pilot.sha(RUN/'random-edges.json.gz')
    params=load(ROOT/'checkpoint.json');assert params['sha']==pilot.sha(RUN/'best.pt')
    put(HERE/'prediction-plan.json',dict(plan=pilot.sha(HERE/'protocol-lock.json'),edges=pilot.sha(HERE/'edge-invariants.json'),source=pilot.sha(HERE/'intervene.py'),primary=pilot.sha(ROOT/'forecast-seal.json'),weights=params['sha'],device=device))
    ptr=load_rgcn_checkpoint(RUN/'best.pt',map_location='cpu')
    m=build_model_from_config(model_cfg);m.load_state_dict(ptr.payload['model_state_dict']);m=m.to(device).eval()
    rewired=load(RUN/'random-edges.json.gz');tids={r['q']:r['t'] for r in split('test')}
    tasks,_,_=materialize('test');scores={}
    lookup={v['t']:v for v in load(HERE/'topologies.json.gz')}
    edges={}
    orig={}
    for t,arr in rewired.items():
        data=torch.tensor(arr,dtype=torch.long).reshape(-1,3).T.contiguous()
        edges[t]=(data[:2],data[2],torch.ones(data.shape[1],dtype=torch.float32))
    for arm in ('native','random','empty'):
        selected=[]
        for task in tasks:
            g=task.graph_tensor;t=tids[g.task_id]
            if arm=='native':selected.append(task);continue
            e,r,w=edges[t] if arm=='random' else (g.edge_index[:,:0],g.relation_ids[:0],g.edge_weights[:0])
            assert (e.shape[1]==lookup[t]['msg_edges'] if arm=='random' else e.shape[1]==0)
            ng=replace(g,edge_index=e,relation_ids=r,edge_weights=w)
            assert ng.node_embeddings.data_ptr()==g.node_embeddings.data_ptr() and ng.node_features.data_ptr()==g.node_features.data_ptr()
            selected.append(replace(task,graph_tensor=ng))
        result={}
        with torch.inference_mode():
            for b in build_evidence_dataloader(selected,per_device_graph_batch_size=128,shuffle=False,random_seed=13):
                logits=m(move_training_batch(b,device))
                for q,rows in split_batch_node_scores(b,logits).items():
                    assert q not in result;result[q]=dict(rows)
        scores[arm]=result
    outputs=[];max_dev=0.;nr_match=0;n_anchored=0;totals=0
    for i in range(8):
        primary=load(ROOT/f'forecasts-rgcn-{i}.json.gz')
        for row in primary:
            q=row['q'];t=row['t'];old={x['node_id']:x for x in row['rr']};orders={};selections={}
            for arm,byq in scores.items():
                V=byq[q];assert set(V)==set(old)
                order=sorted(V,key=lambda k:(-V[k],k));rr=tuple(RankedNodeRecord.model_validate(dict(old[k],score=V[k])) for k in order)
                orders[arm]=order;selections[arm]=[x.node_id for x in pilot.pack(rr,{},2048,'prefix')]
                if arm=='native':
                    for k,s in V.items():max_dev=max(max_dev,abs(s-old[k]['score']))
                    nr_match+=len(order)==len(row['rr']) and order==[u['node_id'] for u in row['rr']]
                    n_anchored+=selections[arm]==row['arms']['prefix']
            outputs.append(dict(q=q,t=t,orders=orders,chosen=selections));totals+=len(old)
    assert len(outputs)==2000 and max_dev<1e-3
    put(HERE/'forecasts.json.gz',outputs);put(HERE/'forecast-seal.json',dict(plan=pilot.sha(HERE/'prediction-plan.json'),out=pilot.sha(HERE/'forecasts.json.gz'),primary_numerical_recheck_max_abs=max_dev,native_full_orders_agree=nr_match,native_prefix_agree=n_anchored,n_queries=len(outputs),candidate_occurrences=totals,seconds=time.monotonic()-start))
def score():
    import dataclasses
    from statistics import mean
    from evaluate import compare
    seal=load(HERE/'forecast-seal.json');assert seal['out']==pilot.sha(HERE/'forecasts.json.gz')
    gt=load(R18/'isetrace_official/gold-spans.json.gz');src={v['q']:v for v in load(HERE/'forecasts.json.gz')}
    rows=[];by=defaultdict(dict)
    for i in range(8):
        for real in load(ROOT/f'forecasts-rgcn-{i}.json.gz'):
            q=real['q'];r=src[q];nodes={n['node_id']:pilot.RankedNodeRecord.model_validate(n) for n in real['rr']}
            gold=tuple(pilot.SourceSpan.model_validate(x) for x in gt[q]);pos={k:j for j,k in enumerate(r['orders']['native'])}
            for a,order in r['orders'].items():
                seen=tuple(nodes[k] for k in r['chosen'][a])
                m=pilot.span_metrics_under_token_budget(seen,gold,2048)
                entry=dict(q=q,t=r['t'],method=a,tokens=sum(n.token_count for n in seen),nodes=len(seen),top1_changed=order[0]!=r['orders']['native'][0],mean_abs_rank_delta=mean(abs(j-pos[k]) for j,k in enumerate(order)),**dataclasses.asdict(m))
                rows.append(entry);by[a][q]=entry
    assert set(by['native'])==set(gt) and len(rows)==6000
    met={a:{k:mean(r[k] for r in qs.values()) for k in ('coverage','density','f1','full_support','tokens','top1_changed','mean_abs_rank_delta')}|dict(hits=int(sum(r['full_support'] for r in qs.values()))) for a,qs in by.items()}
    contrasts={a:compare(by['native'],by[a]) for a in ('random','empty')}
    put(HERE/'outcomes.json.gz',rows);put(HERE/'results.json',dict(metrics=met,paired_native_minus=contrasts))
if __name__=='__main__':{'rank':rank,'score':score}[sys.argv[1]]()

