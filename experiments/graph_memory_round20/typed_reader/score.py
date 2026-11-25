"""Evaluate already-sealed selections with the published span scorer and independent interval-union implementation."""
import collections
import dataclasses
import importlib.util
import math
import sys
import time
from pathlib import Path
import numpy as np
import study as s
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan
spec=importlib.util.spec_from_file_location("verify_interval",""+str(s.HERE.parent.parent/"graph_memory_round17/isetrace/verify_records.py"))
ind=importlib.util.module_from_spec(spec);spec.loader.exec_module(ind)
FIELDS=("full_support","coverage","density","f1","tokens","nodes")

def infer(rows):
    means={}
    by=collections.defaultdict(dict)
    for r in rows:by[r["arm"]+"/"+r["policy"]][r["q"]]=r
    for k,g in by.items():
        means[k]={f:float(np.mean([r[f] for r in g.values()])) for f in FIELDS}
        means[k]["hits"]=round(means[k]["full_support"]*len(g))
        means[k]["n"]=len(g)
    pairs={}
    contrasts=[("typed","dense"),("typed","rank_only"),("typed","untyped"),("typed","shuffled"),
               ("typed","typed_on_shuffled"),("rank_only","dense"),("untyped","dense")]
    seed=13
    for policy in ("prefix","skip"):
        for a,b in contrasts:
            left=by[a+"/"+policy];right=by[b+"/"+policy]
            if not left or not right:continue
            assert set(left)==set(right)
            k=f"{a}-{b}/{policy}"
            groups=collections.defaultdict(list)
            for q in sorted(left):
                groups[left[q]["t"]].append([left[q][z]-right[q][z] for z in ("full_support","coverage")])
            arr=np.array([np.sum(v,axis=0) for _,v in sorted(groups.items())])
            den=np.array([len(v) for _,v in sorted(groups.items())])
            d=np.array([v for vs in groups.values() for v in vs])
            rng=np.random.default_rng(seed)
            sim=[]
            for _ in range(40):
                idx=rng.integers(0,len(arr),size=(250,len(arr)))
                sim.extend(arr[idx].sum(axis=1)/den[idx].sum(axis=1)[:,None])
            ci=np.quantile(sim,[.025,.975],axis=0)
            pairs[k]={f:dict(delta=float(d[:,j].mean()),ci=ci[:,j].tolist(),win=int(np.sum(d[:,j]>1e-13)),
                  loss=int(np.sum(d[:,j]< -1e-13)),ties=int(np.sum(abs(d[:,j])<=1e-13))) for j,f in enumerate(("full_support","coverage"))}
    return dict(means=means,pairs=pairs)

def score(base,seal_file="forecast-seal.json"):
    seal=s.read(base/seal_file)
    assert seal["q"]==2000 and seal["t"]==1207
    gold=s.read(s.OFF/"gold-spans.json.gz")
    result=[];seen=set()
    for i in range(8):
        p=base/f"forecast-{i}.json.gz"
        assert s.sha(p)==seal["forecasts"][p.name]
        maps={r["q"]:r["rr"] for r in s.read(s.TR/f"forecasts-main-{i}.json.gz")}
        for rec in s.read(p):
            q=rec["q"];assert q not in seen
            seen.add(q)
            raw=maps[q]
            nodes=tuple(RankedNodeRecord.model_validate(r) for r in raw)
            gs=tuple(SourceSpan.model_validate(v) for v in gold[q])
            for arm,pol in rec["selection"].items():
                for policy,ids in pol.items():
                    assert len(set(ids))==len(ids)
                    selected=tuple(nodes[i] for i in ids)
                    used=sum(n.token_count for n in selected)
                    assert used<=2048
                    v=span_metrics_under_token_budget(selected,gs,2048)
                    ans=ind.metrics(gold[q],[raw[i] for i in ids])
                    assert all(abs(val-getattr(v,f))<1e-12 for val,f in zip(ans,("coverage","density","full_support"),strict=True))
                    result.append(dict(q=q,t=rec["t"],policy=policy,arm=arm,**dataclasses.asdict(v),tokens=used,nodes=len(ids)))
    assert seen==set(gold) and len(seen)==2000
    s.put(base/"outcomes.json.gz",result)
    out=infer(result)
    s.put(base/"results.json",out)
    print({k:round(v["full_support"],5) for k,v in out["means"].items()},flush=True)
    print("primary",out["pairs"].get("typed-dense/prefix"),flush=True)
if __name__=="__main__":
    score(s.HERE if len(sys.argv)==1 else Path(sys.argv[1]))
