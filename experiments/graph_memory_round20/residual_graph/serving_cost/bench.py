"""Paired warm CPU graph-vs-degree online scoring with identical native cosine inputs."""
from collections import defaultdict
from pathlib import Path
import argparse
import gc
import hashlib
import json
import os
import platform
import sqlite3
import sys
import time

for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','RAYON_NUM_THREADS'):
    os.environ[key]='1'
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SERIES=ROOT.parent
sys.path.insert(0,str(ROOT/'cpu_fallback'))
sys.path.insert(1,str(ROOT))
import numpy as np
import torch
from fallback import data
from fit_graph import features,model_cfg,build_model_from_config,tensorize_provenance_ranking_task
from setup_graph import RUN,TR,pilot,load,put
from data import graphfiles,split
from forecasts import Lookup
from graph_memory.models.graph_retriever.batching import collate_evidence_tasks
from graph_memory.models.graph_retriever.checkpoint import load_rgcn_checkpoint
from graph_memory.graphs.provenance import (ARGUMENT_CHUNK_NODE,OUTPUT_CHUNK_NODE,HAS_ARGUMENT_EDGE,HAS_CONTENT_EDGE,
    RETURNS_EDGE,NEXT_CHUNK_EDGE,FEEDS_EDGE,RESOURCE_FLOW_RELATION,logical_output_dependencies)

F=SERIES/'factor_reader'
D=SERIES/'typed_reader'
spec=__import__('importlib.util',fromlist=['util'])
mod=spec.spec_from_file_location('audit_degrees_reference',D/'study.py')
ref=spec.module_from_spec(mod);mod.loader.exec_module(ref)
START=time.perf_counter_ns

def lock():
    assert not (HERE/'plan.json').exists()
    ids=[r['q'] for r in split('test')]
    digest=lambda q:hashlib.sha256(('R20 gate runtime v1|'+q).encode()).digest()
    ids=sorted(ids,key=digest)[:96]
    assert ids==load(SERIES/'graph_trigger/hash64-runtime.json')['q']
    put(HERE/'plan.json',dict(q=ids,n=len(ids),seed=13,bootstrap=10000,blocks=8,
        code=pilot.sha(HERE/'bench.py'),protocol=pilot.sha(HERE/'PROTOCOL_RU.md'),
        prior=pilot.sha(F/'prior.json'),rank=pilot.sha(F/'hash64-weights.json'),
        factor_forecasts=pilot.sha(F/'hash64-seal.json'),hash64_forecasts=pilot.sha(ROOT/'cpu_fallback/hash64/forecast-seal.json')))

def prior_rows(graph,prior):
    ids=sorted(n.node_id for n in graph.nodes if n.kind in (ARGUMENT_CHUNK_NODE,OUTPUT_CHUNK_NODE))
    pos={k:i for i,k in enumerate(ids)}
    args,outs=defaultdict(list),defaultdict(list)
    child={};edges=set()
    def link(x,y,k):
        if x!=y and x in pos and y in pos:edges.add((pos[x],pos[y],k))
    for e in graph.edges:
        if e.relation==HAS_ARGUMENT_EDGE:args[e.source].append(e.target)
        elif e.relation==HAS_CONTENT_EDGE:outs[e.source].append(e.target)
        elif e.relation==RETURNS_EDGE:child[e.source]=e.target
        elif e.relation==NEXT_CHUNK_EDGE:link(e.source,e.target,0)
    for call,terms in args.items():
        for x in terms:
            for y in outs.get(child.get(call),[]):link(x,y,1)
    for dep in logical_output_dependencies(graph):
        assert dep.relation in (FEEDS_EDGE,RESOURCE_FLOW_RELATION)
        for x in outs.get(dep.source_output_id,[]):
            for y in outs.get(dep.target_output_id,[]):link(x,y,2 if dep.relation==FEEDS_EDGE else 3)
    counts=np.zeros((len(ids),8),dtype=np.int32)
    for x,y,k in edges:
        counts[x,2*k]+=1;counts[y,2*k+1]+=1
    compiled=np.log1p(counts.astype('float64'))@np.asarray(prior['coef'])+prior['intercept']
    return pos,counts,compiled

def pinned_orders(targets,base,tag):
    fseal=load(F/'hash64-seal.json')['files']
    gref=load(base/'forecast-seal.json');gseal=gref.get('files',gref.get('forecasts'))
    originals={};struct={};native={}
    for i in range(8):
        dn=f'forecasts-main-{i}.json.gz'
        assert load(TR/'forecast-seal.json')['forecasts'][dn]==pilot.sha(TR/dn)
        for r in load(TR/dn):
            if r['q'] in targets:originals[r['q']]=[n['node_id'] for n in r['rr']]
        fn=f'hash64-ranks-{i}.json.gz';assert fseal[fn]==pilot.sha(F/fn)
        for r in load(F/fn):
            if r['q'] in targets:struct[r['q']]=[originals[r['q']][j] for j in r['ranks']['degree']]
        gn=f'forecasts-rgcn-{i}.json.gz';assert gseal[gn]==pilot.sha(base/gn)
        for r in load(base/gn):
            if r['q'] in targets:native[r['q']]=[(n['node_id'],n['score']) for n in r['rr']]
    assert set(originals)==set(native)==set(struct)==targets
    return originals,struct,native

def prepare(tag,ids):
    parent=ROOT/'cpu_fallback/hash64' if tag=='hash64' else ROOT
    base=parent/'best.pt'
    assert pilot.sha(base)==load(parent/'checkpoint.json')['sha']
    dense,reference,expected_native=pinned_orders(set(ids),parent,tag)
    params=load(F/'prior.json')['models']['degree']; rank=load(F/'hash64-weights.json')['rank']
    weights=np.array(rank['coef']);intercept=rank['intercept']
    load_start=START()
    model=build_model_from_config(model_cfg).eval()
    model.load_state_dict(load_rgcn_checkpoint(base,map_location='cpu').payload['model_state_dict'])
    conn=sqlite3.connect((RUN/'vectors.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
    coder=Lookup(conn,'ft')
    setup_boot=START()-load_start
    want={r['t'] for r in split('test') if r['q'] in ids}; tasks={}; per_t={}; at={}
    idx=ref.graph_index();files=graphfiles()
    for t,requests,labels in data('test',want):
        assert not labels
        graph=requests[0].graph
        raw_bytes=files[t][0].stat().st_size
        t0=START();pos,counts,vec=prior_rows(graph,params);index_ns=START()-t0
        oracle_ix,ch,_,_,_=ref.project(t,idx)
        oracle=np.column_stack([np.bincount(x[0],minlength=len(oracle_ix)) for x in ch])
        assert pos==oracle_ix and np.array_equal(oracle,counts)
        requests=[r for r in requests if r.task_id in ids]
        n=len(graph.nodes)+1;buf=np.empty((len(requests)*n,768),dtype='<f4')
        tm=START();provider,end=features(requests,coder,buf,0);feed=START()-tm
        assert end==len(buf)
        per_t[t]=dict(candidates=len(pos),nodes=len(graph.nodes),edges=len(graph.edges),queries=len(requests),
            graph_gzip_bytes=raw_bytes,compiled_score_bytes=vec.nbytes,eight_counts_bytes=counts.nbytes,
            shared_passage_embedding_payload=len(graph.nodes)*768*4,query_embedding_payload=len(requests)*768*4,
            reference_lookup_and_copy_ns=feed,degree_build_ns=index_ns)
        for req in requests:
            q=req.task_id
            tm=START()
            task=tensorize_provenance_ranking_task(req,model_config=model_cfg,text_embedding_provider=provider,seed_signal_provider=provider)
            material_ns=START()-tm
            tm=START();b=collate_evidence_tasks([task]);collate_ns=START()-tm
            index=list(b.sample_node_ids)
            assert len(set(index))==len(pos) and set(index)==set(pos)
            s=b.sample_node_features[:,0].detach().numpy()
            tm=START();aligned=np.asarray([vec[pos[k]] for k in index]);align_ns=START()-tm
            by_id={c.item_id:c.metadata['token_count'] for c in req.candidates}
            costs=np.array([by_id[k] for k in index],dtype=int)
            # The shared semantic input originates in the actual native batch. Stable tie-break first by ID.
            tie=np.array(sorted(range(len(index)),key=lambda i:index[i]))
            order=tie[np.argsort(-s[tie],kind='stable')]
            seed_order=[index[k] for k in order]
            frozen_ok=(seed_order==dense[q])
            tasks[q]=dict(batch=b,task=task,ids=index,seed=s,prior=aligned,tie=tie,cost=costs,
                          rankweights=weights,intercept=intercept)
            at[q]=dict(t=t,candidates=len(index),native_tensorize_ns=material_ns,native_collate_ns=collate_ns,prior_alignment_ns=align_ns,
                dense_order_equal=frozen_ok,shared_seed_sha=hashlib.sha256(s.astype('<f4').tobytes()).hexdigest())
    assert set(tasks)==set(ids)
    return model,tasks,at,per_t,reference,expected_native,setup_boot,base

def context(order,ts):
    used=0;prefix=[]
    for i in order:
        n=ts['cost'][i]
        if used+n>2048:break
        used+=n;prefix.append(ts['ids'][i])
    return [ts['ids'][i] for i in order],prefix

def factor(ts):
    perm=ts['tie'][np.argsort(-ts['seed'][ts['tie']],kind='stable')]
    n=len(perm);r=np.arange(1,n+1)
    features=np.column_stack((-np.log(r),1/r,(n-r)/max(1,n-1)))
    scores=features@ts['rankweights']+ts['intercept']+ts['prior'][perm]
    return context(perm[np.argsort(-scores,kind='stable')],ts)

def native(ts,m):
    y=m(ts['batch']).detach().numpy()
    order=ts['tie'][np.argsort(-y[ts['tie']],kind='stable')]
    return context(order,ts)

def signature(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def summarize(records,queries):
    stats={}
    a=[];b=[];by=defaultdict(list)
    for q in queries:
        f=np.array([r['degree_ns'] for r in records if r['q']==q]);g=np.array([r['native_ns'] for r in records if r['q']==q])
        a.append(np.median(f));b.append(np.median(g));t=next(v['t'] for v in records if v['q']==q)
        by[t].append([np.median(f),np.median(g)])
    a,b=np.asarray(a),np.asarray(b);keys=sorted(by);tot=np.stack([np.sum(by[t],axis=0) for t in keys])
    rng=np.random.default_rng(13);ix=rng.integers(0,len(keys),(10000,len(keys)))
    summed=tot[ix].sum(axis=1);boot=summed[:,0]/summed[:,1]
    for name,v in [('degree_ns',a),('native_ns',b)]:
        stats[name]=dict(p50=float(np.median(v)),p95=float(np.quantile(v,.95)),mean=float(v.mean()))
    stats['ratio_mean']=float(a.sum()/b.sum());stats['ratio_ci95']=np.quantile(boot,[.025,.975]).tolist()
    stats['median_paired_ratio']=float(np.median(a/b))
    return stats

def run(tag):
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    plan=load(HERE/'plan.json')
    assert plan['code']==pilot.sha(HERE/'bench.py') and plan['prior']==pilot.sha(F/'prior.json') and plan['rank']==pilot.sha(F/'hash64-weights.json')
    ids=plan['q'];m,tasks,at,trees,expected_deg,expected_g,setup,base=prepare(tag,ids)
    records=[];refs={}
    with torch.inference_mode():
        for q in ids:
            t=tasks[q];d=factor(t);g=native(t,m)
            y=m(t['batch']).detach().numpy()
            scores=dict(zip(t['ids'],y.tolist(),strict=True))
            gap=max(abs(scores[k]-s) for k,s in expected_g[q])
            assert gap<.002 and set(g[0])==set(d[0])==set(t['ids'])
            orig_g=[k for k,_ in expected_g[q]]
            cot=lambda order:context(np.asarray([t['ids'].index(k) for k in order]),t)[1]
            at[q].update(degree_full_order_equal=d[0]==expected_deg[q],degree_prefix_equal=d[1]==cot(expected_deg[q]),
                         native_full_order_equal=g[0]==orig_g,native_prefix_equal=g[1]==cot(orig_g),native_max_score_error=gap)
            refs[q]={'degree':d,'native':g}
        old=gc.isenabled()
        if old:gc.disable()
        try:
            for block in range(plan['blocks']):
                for j,q in enumerate(ids):
                    order=('degree','native') if (block+j)%2==0 else ('native','degree')
                    times={};result={}
                    for arm in order:
                        begin=START();value=factor(tasks[q]) if arm=='degree' else native(tasks[q],m)
                        times[arm+'_ns']=START()-begin;result[arm]=value
                    assert result==refs[q]
                    records.append({'q':q,'t':at[q]['t'],'block':block,'first':order[0],**times})
        finally:
            if old:gc.enable()
    pp=HERE/f'{tag}-measurements.json.gz'
    put(pp,{'times':records,'queries':at,'trajectories':trees,'paired_output_sha':{q:{k:signature(v) for k,v in arm.items()} for q,arm in refs.items()}})
    idmatch={k:sum(v[k] for v in at.values()) for k in ('dense_order_equal','degree_full_order_equal','degree_prefix_equal','native_full_order_equal','native_prefix_equal')}
    report=dict(plan=pilot.sha(HERE/'plan.json'),measurements=pilot.sha(pp),n=len(at),trajectories=len(trees),blocks=plan['blocks'],
         match=idmatch,worst_native_score_error=max(v['native_max_score_error'] for v in at.values()),
         source_graph_gzip_bytes=sum(v['graph_gzip_bytes'] for v in trees.values()),
         common_graph_passage_embedding_bytes_before_intertrajectory_dedup=sum(v['shared_passage_embedding_payload'] for v in trees.values()),
         common_query_embedding_bytes=sum(v['query_embedding_payload'] for v in trees.values()),
         degree_store=dict(eight_int32_bytes=sum(v['eight_counts_bytes'] for v in trees.values()),float64_scalar_bytes=sum(v['compiled_score_bytes'] for v in trees.values())),
         model=dict(rgcn_checkpoint_bytes=base.stat().st_size,rgcn_sha=pilot.sha(base),degree_and_rank_weight_bytes=13*8),
         baseline_loading_ns=setup,prior_build_ns=sum(v['degree_build_ns'] for v in trees.values()),
         native_collate_ns=sum(v['native_collate_ns'] for v in at.values()),native_tensorize_ns=sum(v['native_tensorize_ns'] for v in at.values()),
         alignment_ns=sum(v['prior_alignment_ns'] for v in at.values()),
         frozen_vector_lookup_copy_ns=sum(v['reference_lookup_and_copy_ns'] for v in trees.values()),
         online=summarize(records,ids),platform=platform.platform(),cpu=platform.processor(),numpy=np.__version__,torch=torch.__version__,
         threads=torch.get_num_threads(),interop_threads=torch.get_num_interop_threads(),device='cpu',batch=1)
    put(HERE/f'{tag}-cost.json',report)
    print(tag,idmatch,report['online'],flush=True)

if __name__=='__main__':
    if sys.argv[1]=='lock':lock()
    else:run(sys.argv[1])
