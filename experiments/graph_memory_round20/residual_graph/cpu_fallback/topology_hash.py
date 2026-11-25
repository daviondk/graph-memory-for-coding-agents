"""Evaluate frozen-weight graph perturbations on the hash-selected reduced-training checkpoint."""
from pathlib import Path
from dataclasses import replace
from collections import defaultdict
from statistics import mean
import hashlib,sys,time,torch,numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from setup_graph import ROOT,RUN,R18,load,put,pilot
from data import streams,graphfiles
from vectors import database
from forecasts import Lookup
from fit_graph import build_model_from_config,model_cfg,features,tensorize_provenance_ranking_task
from graph_memory.models.graph_retriever.batching import collate_evidence_tasks,split_batch_node_scores
from graph_memory.models.graph_retriever.checkpoint import load_rgcn_checkpoint
from evaluate import compare
def lock():
    put(HERE/'topology-plan.json',dict(source=pilot.sha(HERE/'topology_hash.py'),protocol=pilot.sha(HERE/'TOPOLOGY_RU.md'),cohorts=pilot.sha(HERE/'cohorts.json'),invariants=pilot.sha(ROOT/'topology/edge-invariants.json')))
def run():
    sub=HERE/'hash64';assert load(HERE/'topology-plan.json')['source']==pilot.sha(HERE/'topology_hash.py')
    native=load(sub/'forecast-seal.json');assert all(pilot.sha(sub/f)==v for f,v in native['files'].items())
    ck=load(sub/'checkpoint.json');assert pilot.sha(sub/'best.pt')==ck['sha']
    src=load(ROOT/'topology/edge-invariants.json');assert pilot.sha(RUN/'random-edges.json.gz')==src['transformed_sha']
    alt=load(RUN/'random-edges.json.gz');torch.set_num_threads(8)
    m=build_model_from_config(model_cfg);m.load_state_dict(load_rgcn_checkpoint(sub/'best.pt',map_location='cpu').payload['model_state_dict']);m.eval()
    rows=[];pending=[];lk=Lookup(database(),'ft');base={}
    for f in sub.glob('forecasts-rgcn-*.json.gz'):
        for r in load(f):base[r['q']]=r
    def flush():
        ids=[t for _,t,_ in pending]
        scores={}
        for arm,ix in [('native',0),('random',1),('empty',2)]:
            b=collate_evidence_tasks([ls[ix] for _,_,ls in pending])
            with torch.inference_mode():values=m(b)
            scores[arm]=split_batch_node_scores(b,values)
        for r,t,_ in pending:
            q=r.task_id;pool={v['node_id']:v for v in base[q]['rr']};chosen={};order={}
            for arm,byq in scores.items():
                arr=sorted(byq[q],key=lambda a:(-a[1],a[0]));order[arm]=[k for k,_ in arr];assert set(order[arm])==set(pool)
                rr=tuple(pilot.RankedNodeRecord.model_validate(dict(pool[k],score=z)) for k,z in arr)
                chosen[arm]=[n.node_id for n in pilot.pack(rr,{},2048,'prefix')]
            rows.append(dict(q=q,t=t,orders=order,chosen=chosen))
        pending.clear()
    for t,rs,_ in streams('test'):
        f=np.empty((len(rs)*(len(rs[0].graph.nodes)+1),768),dtype='<f4');prov,_=features(rs,lk,f,0)
        e=torch.tensor(alt[t],dtype=torch.long).reshape(-1,3).T.contiguous()
        for r in rs:
            a=tensorize_provenance_ranking_task(r,model_config=model_cfg,seed_signal_provider=prov,text_embedding_provider=prov)
            g=a.graph_tensor
            b=replace(a,graph_tensor=replace(g,edge_index=e[:2],relation_ids=e[2],edge_weights=torch.ones(e.shape[1])))
            d=replace(a,graph_tensor=replace(g,edge_index=g.edge_index[:,:0],relation_ids=g.relation_ids[:0],edge_weights=g.edge_weights[:0]))
            assert a.graph_tensor.node_embeddings.data_ptr()==b.graph_tensor.node_embeddings.data_ptr()==d.graph_tensor.node_embeddings.data_ptr()
            pending.append((r,t,(a,b,d)))
            if len(pending)==64:flush()
    if pending:flush()
    assert len(rows)==len(base)==2000
    put(sub/'topology-forecasts.json.gz',rows);put(sub/'topology-seal.json',dict(source=pilot.sha(HERE/'topology-plan.json'),pred=pilot.sha(sub/'topology-forecasts.json.gz'),weights=ck['sha'],native_prefix_agree=sum(r['chosen']['native']==base[r['q']]['arms']['prefix'] for r in rows)))
def score():
    import dataclasses
    sub=HERE/'hash64';seal=load(sub/'topology-seal.json');assert seal['pred']==pilot.sha(sub/'topology-forecasts.json.gz')
    truth=load(R18/'isetrace_official/gold-spans.json.gz');rows={v['q']:v for v in load(sub/'topology-forecasts.json.gz')};stored=[];sets=defaultdict(dict)
    for fn in sub.glob('forecasts-rgcn-*.json.gz'):
        for base in load(fn):
            q,t=base['q'],base['t'];r=rows[q];nodes={v['node_id']:pilot.RankedNodeRecord.model_validate(v) for v in base['rr']};gs=tuple(pilot.SourceSpan.model_validate(s) for s in truth[q])
            for arm,ids in r['chosen'].items():
                nn=tuple(nodes[k] for k in ids);metrics=pilot.span_metrics_under_token_budget(nn,gs,2048)
                val=dict(q=q,t=t,arm=arm,tokens=sum(v.token_count for v in nn),nodes=len(nn),**dataclasses.asdict(metrics))
                sets[arm][q]=val;stored.append(val)
    sums={name:dict(n=len(arr),hits=int(sum(r['full_support'] for r in arr.values())),coverage=mean(r['coverage'] for r in arr.values()),tokens=mean(r['tokens'] for r in arr.values())) for name,arr in sets.items()}
    pairs={name:compare(sets['native'],sets[name]) for name in ('random','empty')}
    put(sub/'topology-outcomes.json.gz',stored);put(sub/'topology-results.json',dict(metrics=sums,paired=pairs))
if __name__=='__main__':{'lock':lock,'rank':run,'score':score}[sys.argv[1]]()

