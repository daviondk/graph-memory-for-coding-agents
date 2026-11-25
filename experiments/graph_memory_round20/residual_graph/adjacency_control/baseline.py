"""Retrain the authors' strongest reported topology ablation, including checkpoint selection."""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from shutil import copyfile
import argparse
import sys
import hashlib

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
sys.path.insert(0,str(PARENT))
import fit_graph as fit
import infer_graph as inf
from setup_graph import RUN,load,put,pilot
from graph_memory.models.graph_retriever import provenance
sys.path.insert(0,str(PARENT/'cpu_fallback'))
import fallback
import read as reduced
import evaluate_graph

HASH='hash64'
FULL='full'
PRIVATE=RUN/'adjacency-control'
CFG=fit.model_cfg
NO_NEXT=fit.provenance_rgcn_model_config(encoder_model=CFG.encoder_model,encoder_dim=CFG.encoder_dim,
    query_prefix=CFG.query_prefix,passage_prefix=CFG.passage_prefix,encoder_batch_size=CFG.encoder_batch_size,
    hidden_dim=CFG.hidden_dim,num_layers=CFG.num_layers,dropout=CFG.dropout,ablation_name='wo_chunk_adjacency')
def stage_dir(tag):
    dest=HERE/tag
    private=PRIVATE/tag
    dest.mkdir(exist_ok=True);private.mkdir(parents=True,exist_ok=True)
    return dest,private

def base_parent(tag):
    return PARENT if tag==FULL else PARENT/'cpu_fallback'/tag

def lock():
    ds=[k for k,v in NO_NEXT.model_dump().items() if CFG.model_dump()[k]!=v]
    assert set(ds)=={'ablation_name','enabled_provenance_relations'}
    assert set(CFG.enabled_provenance_relations)-set(NO_NEXT.enabled_provenance_relations)=={'content.next'}
    assert NO_NEXT.relation_vocab==CFG.relation_vocab and len(CFG.relation_vocab)==14
    paths=[HERE/'PROTOCOL_RU.md',HERE/'baseline.py',PARENT/'fit_graph.py',PARENT/'infer_graph.py',
           PARENT/'cpu_fallback/fallback.py',PARENT/'cpu_fallback/read.py',Path(provenance.__file__).resolve()]
    assert not (HERE/'plan.json').exists()
    put(HERE/'plan.json',dict(files={p.relative_to(PARENT).as_posix() if p.is_relative_to(PARENT) else 'upstream/provenance.py':pilot.sha(p) for p in paths},
        training=fit.training.model_dump(),old=CFG.model_dump(),new=NO_NEXT.model_dump(),
        ft_id=load(PARENT/'vectors-plan.json')['FT'],mining=fit.mining.model_dump(),seed=13))

def change(tag):
    dest,private=stage_dir(tag)
    plan=load(HERE/'plan.json')
    assert plan['files']['adjacency_control/baseline.py']==pilot.sha(HERE/'baseline.py')
    assert plan['new']==NO_NEXT.model_dump(mode='json')
    stack=ExitStack()
    stack.enter_context(patch.object(fit,'model_cfg',NO_NEXT))
    if tag==HASH:
        stack.enter_context(patch.object(reduced,'model_cfg',NO_NEXT))
        for mod in (fallback,reduced):
            stack.enter_context(patch.object(mod,'dirs',lambda name:(dest,private)))
    else:
        for mod in (fit,inf):
            stack.enter_context(patch.multiple(mod,ROOT=dest,RUN=private))
        stack.enter_context(patch.object(inf,'model_cfg',NO_NEXT))
    return stack

def train(tag):
    dest,private=stage_dir(tag)
    parent=base_parent(tag)
    assert (parent/'checkpoint.json').exists()
    if tag==FULL:
        # Pair mining uses the original graph's neighbor annotations in the native pipeline.
        copyfile(parent/'train-pairs.json.gz',dest/'train-pairs.json.gz')
    put(dest/'model-lock.json',{'plan':pilot.sha(HERE/'plan.json'),'canonical_pairs':pilot.sha(parent/'train-pairs.json.gz'),
        'canonical_checkpoint':pilot.sha(parent/'checkpoint.json'),'n':3894 if tag==FULL else 101})
    with change(tag):
        if tag==HASH:
            fallback.train(tag)
        else:
            fit.fit()
    assert load(dest/'train-pairs.json.gz')==load(parent/'train-pairs.json.gz')
    if tag==FULL:
        copyfile(private/'best.pt',dest/'best.pt')
    assert pilot.sha(dest/'best.pt')==load(dest/'checkpoint.json')['sha']

def rank(tag):
    dest,private=stage_dir(tag)
    assert load(dest/'model-lock.json')['canonical_pairs']==pilot.sha(base_parent(tag)/'train-pairs.json.gz')
    with change(tag):
        if tag==HASH:
            reduced.rank(tag)
        else:
            put(dest/'prediction-plan.json',dict(files={k:pilot.sha(dest/k) for k in ['checkpoint.json','train-pairs.json.gz','model-lock.json']},
                ranker=pilot.sha(PARENT/'infer_graph.py'),method=pilot.sha(HERE/'baseline.py')))
            inf.infer()

def score(tag):
    dest,_=stage_dir(tag)
    with change(tag):
        if tag==HASH:
            reduced.score(tag)
        else:
            with patch.object(evaluate_graph,'ROOT',dest):evaluate_graph.main()
    from evaluate import compare
    def means(path):
        return {r['q']:r for r in load(path/'outcomes.json.gz') if r.get('stage','test')=='test' and r['arm']=='prefix' and r['method']=='rgcn'}
    orig=base_parent(tag)
    A=means(dest);B=means(orig)
    structural_path=PARENT.parent/'factor_reader/hash64-outcomes.json.gz'
    structural=load(structural_path)['prefix/degree']
    assert len(A)==2000 and set(A)==set(B)==set(structural)
    assert all(A[q]['t']==B[q]['t']==structural[q]['t'] for q in A)
    def contrast(left,right):
        import numpy as np
        from collections import defaultdict
        fields=('full_support','coverage')
        by=defaultdict(list)
        for q in sorted(left):
            by[left[q]['t']].append([left[q][k]-right[q][k] for k in fields])
        groups=sorted(by);counts=np.array([len(by[g]) for g in groups])
        totals=np.stack([np.sum(by[g],axis=0) for g in groups]);values=totals.sum(axis=0)/counts.sum()
        rng=np.random.default_rng(13);samples=[]
        for i in range(0,10000,64):
            ix=rng.integers(0,len(groups),size=(min(64,10000-i),len(groups)))
            samples.append(totals[ix].sum(axis=1)/counts[ix].sum(axis=1)[:,None])
        ci=np.quantile(np.concatenate(samples),[.025,.975],axis=0)
        return dict(trajectories=len(groups),differences={k:dict(estimate=float(values[j]),cluster_ci95=ci[:,j].tolist()) for j,k in enumerate(fields)})
    out={'trained_ablation_minus_native':contrast(A,B),'degree_minus_trained_ablation':contrast(structural,A)}
    put(dest/'matched-comparisons.json',dict(n=2000,comparisons=out,fs_hits={k:int(sum(r['full_support'] for r in v.values()))
        for k,v in [('native',B),('no_next',A),('degree_hash64',structural)]},
        outcomes=pilot.sha(dest/'outcomes.json.gz'),reference=pilot.sha(orig/'outcomes.json.gz'),
        structural=pilot.sha(structural_path)))
    print(tag,[(k,v['differences']['full_support']) for k,v in out.items()],flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=['lock','fit','rank','score'])
    ap.add_argument('tag',choices=[FULL,HASH],nargs='?')
    args=ap.parse_args()
    if args.mode=='lock':
        lock()
    else:
        assert args.tag
        {'fit':train,'rank':rank,'score':score}[args.mode](args.tag)
