"""Emit complete native dev and test graph ranks of one reduced-training checkpoint, then score."""
from pathlib import Path
from collections import defaultdict
from statistics import mean
import dataclasses,sys,time,torch
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from fallback import dirs,data
from setup_graph import ROOT,RUN,TR,R18,CACHE,load,put,pilot
from fit_graph import features,model_cfg,build_model_from_config
from vectors import database
from forecasts import Lookup
from graph_memory.models.graph_retriever.provenance import tensorize_provenance_ranking_task
from graph_memory.models.graph_retriever.batching import collate_evidence_tasks,split_batch_node_scores
from graph_memory.models.graph_retriever.checkpoint import load_rgcn_checkpoint
from graph_memory.retrieval.contracts import RankedNode
from graph_memory.evaluation.span_metrics import span_metrics_at,span_mrr
from data import split
from evaluate import compare
import numpy as np
def ranked_batch(pending,model,zero,out,cost):
    if not pending:return
    b=collate_evidence_tasks([v for r,v,t in pending]);start=time.monotonic()
    with torch.inference_mode():a=model(b);n=zero(b)
    assert torch.equal(n,b.sample_node_features[:,0]);cost.append(time.monotonic()-start)
    for method,values in [('rgcn',a),('seed',n)]:
        scores=split_batch_node_scores(b,values)
        for r,task,t in pending:
            q=r.task_id;rank=sorted(scores[q],key=lambda x:(-x[1],x[0]));meta={v.item_id:v.metadata for v in r.candidates}
            assert {v.item_id for v in r.candidates}=={i for i,_ in rank} and len(rank)==len(r.candidates)
            rr=pilot.assemble_ranked_result(request=r,method='provenance_rgcn',ranked_nodes=[RankedNode(node_id=i,score=s) for i,s in rank],top_k=len(rank),latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes
            arms={pol:[v.node_id for v in pilot.pack(rr,meta,2048,pol)] for pol in ('prefix','skip','related')}
            out[method].append(dict(q=q,t=t,rr=[v.model_dump() for v in rr],arms=arms))
def rank(name):
    torch.set_num_threads(8);sub,pri=dirs(name);ck=load(sub/'checkpoint.json');assert ck['sha']==pilot.sha(sub/'best.pt')
    put(sub/'prediction-plan.json',dict(weights=ck['sha'],source=pilot.sha(HERE/'read.py'),fit=pilot.sha(sub/'fit-lock.json'),cohort=pilot.sha(HERE/'cohorts.json')))
    p=load_rgcn_checkpoint(sub/'best.pt',map_location='cpu')
    model=build_model_from_config(model_cfg).eval();model.load_state_dict(p.payload['model_state_dict']);zero=build_model_from_config(model_cfg).eval();c=database();lookup=Lookup(c,'ft');hashes={};tm=time.monotonic()
    for stage in ['dev','test']:
        # Stream one native tensor per graph. Dev labels are outside this ranking path and never feed scores.
        pending=[];results={'rgcn':[],'seed':[]};times=[]
        for t,rs,labels in data(stage):
            n=len(rs[0].graph.nodes)+1;f=np.empty((len(rs)*n,768),dtype='<f4');prov,fin=features(rs,lookup,f,0);assert fin==len(f)
            for r in rs:
                v=tensorize_provenance_ranking_task(r,model_config=model_cfg,text_embedding_provider=prov,seed_signal_provider=prov)
                pending.append((r,v,t))
                if len(pending)==64:ranked_batch(pending,model,zero,results,times);pending=[]
        ranked_batch(pending,model,zero,results,times)
        ids={r['q'] for r in split(stage)}
        for method,rows in results.items():
            assert len(rows)==len(ids) and {r['q'] for r in rows}==ids
            if stage=='dev':
                path=sub/f'dev500-pu-{method}-ranks.json.gz';put(path,rows);hashes[path.name]=pilot.sha(path)
            else:
                from data import graphfiles
                groups=defaultdict(list);allg=graphfiles()
                for r in rows:groups[int(allg[r['t']][0].name.split('-',1)[0])].append(r)
                for j,group in sorted(groups.items()):
                    path=sub/f'forecasts-{method}-{j}.json.gz';put(path,group);hashes[path.name]=pilot.sha(path)
        print(name,stage,len(ids),'two forwards',sum(times),'total',time.monotonic()-tm,flush=True)
    put(sub/'forecast-seal.json',dict(files=hashes,plan=pilot.sha(sub/'prediction-plan.json'),n=2000,n_dev=500,seconds=time.monotonic()-tm))
def score(name):
    sub,pri=dirs(name);seal=load(sub/'forecast-seal.json');assert all(pilot.sha(sub/f)==v for f,v in seal['files'].items())
    maps=defaultdict(dict);outputs=[];summary={}
    for stage in ['test','dev']:
        gt=load(R18/'isetrace_official/gold-spans.json.gz') if stage=='test' else load(TR.parent/'write_transfer/gold-spans.json.gz')
        for method in ('rgcn','seed'):
            files=list(sub.glob(f'forecasts-{method}-*.json.gz')) if stage=='test' else [sub/f'dev500-pu-{method}-ranks.json.gz']
            for f in files:
                for r in load(f):
                    q=r['q'];t=r['t'];g=tuple(pilot.SourceSpan.model_validate(v) for v in gt[q]);rr=tuple(pilot.RankedNodeRecord.model_validate(v) for v in r['rr']);N={v.node_id:v for v in rr}
                    for arm,K in r['arms'].items():
                        S=tuple(N[k] for k in K);m=pilot.span_metrics_under_token_budget(S,g,2048)
                        if arm=='prefix':assert m==pilot.span_metrics_under_token_budget(rr,g,2048)
                        rec=dict(q=q,t=t,stage=stage,method=method,arm=arm,nodes=len(S),tokens=sum(x.token_count for x in S),**dataclasses.asdict(m))
                        if arm=='prefix':rec.update(recall5=span_metrics_at(rr,g,5).coverage,mrr=span_mrr(rr,g))
                        assert rec['tokens']<=2048;key=stage,method+'/'+arm;assert q not in maps[key];maps[key][q]=rec;outputs.append(rec)
        stats={k:{m:mean(r[m] for r in V.values()) for m in ('full_support','coverage','density','f1','tokens','nodes')}|dict(hits=int(sum(r['full_support'] for r in V.values())),n=len(V)) for (st,k),V in maps.items() if st==stage}
        pairs={a+' - '+b:compare(maps[stage,a],maps[stage,b]) for a,b in [('rgcn/prefix','seed/prefix'),('rgcn/related','rgcn/skip'),('rgcn/skip','rgcn/prefix'),('seed/related','seed/skip')]}
        summary[stage]=dict(metrics=stats,contrasts=pairs)
    put(sub/'outcomes.json.gz',outputs);put(sub/'results.json',summary)
    print(name,{'test':{k:r['hits'] for k,r in summary['test']['metrics'].items()}},flush=True)
if __name__=='__main__':{'rank':rank,'score':score}[sys.argv[1]](sys.argv[2])

