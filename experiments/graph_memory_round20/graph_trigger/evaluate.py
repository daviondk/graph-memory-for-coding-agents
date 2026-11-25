"""Score sealed independent routing decisions with the same PU budget and candidate pools."""
import argparse
from collections import Counter
from statistics import mean
import time

import numpy as np
from gate import ROOT,TR,OFF,Path,load,put,sha,hashstr,choose_skip,matched_pool,QUOTAS
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
from graph_memory.trajectories import SourceSpan
from graph_memory.retrieval.results import RankedNodeRecord

FIELDS=("fs","coverage","density","tokens")


def hash_pairs(item):
    if isinstance(item,dict):
        for k,v in item.items():
            if isinstance(v,str):yield k,v
            else:yield from hash_pairs(v)
    elif isinstance(item,list):
        for v in item:yield from hash_pairs(v)


def contrast(rows,a,b):
    groups=sorted({r["t"] for r in rows});group={name:i for i,name in enumerate(groups)}
    ds=np.array([[r[r["methods"][a]][k]-r[r["methods"][b]][k] for k in FIELDS] for r in rows])
    g=np.array([group[r["t"]] for r in rows]);counts=np.bincount(g)
    totals=np.stack([np.bincount(g,weights=ds[:,i]) for i in range(len(FIELDS))],axis=1)
    boot=[];rng=np.random.default_rng(20)
    for _ in range(100):
        draw=rng.integers(len(groups),size=(100,len(groups)))
        boot.append(totals[draw].sum(axis=1)/counts[draw].sum(axis=1)[:,None])
    ci=np.percentile(np.concatenate(boot),[2.5,97.5],axis=0).T
    return dict(n=len(rows),tr=len(groups),win=int((ds[:,0]>0).sum()),lose=int((ds[:,0]<0).sum()),
        metric={k:dict(delta=ds[:,i].mean(),ci=ci[i].tolist()) for i,k in enumerate(FIELDS)})


def main(tag,rank_dir,pattern,rank_seal):
    seal=load(ROOT/(tag+"-decision-seal.json"))
    assert seal["decisions"]==sha(ROOT/(tag+"-decisions.json.gz")) and seal["model"]==sha(ROOT/(tag+"-model.json"))
    assert sha(ROOT/"feature-seal.json")==seal["inputs"]
    files=sorted(rank_dir.glob(pattern));assert files
    registry=dict(hash_pairs(load(rank_seal)));assert all(registry.get(p.name)==sha(p) for p in files)
    dec={r["q"]:r for r in load(ROOT/(tag+"-decisions.json.gz"))}
    x={r["q"]:r for r in load(ROOT/"test-features.json.gz")}
    # This is the only stage that accesses test annotations or previously scored outcomes.
    dl=load(TR/"outcomes.json.gz");dense={r["q"]:dict(fs=int(r["full_support"]),coverage=r["coverage"],
        density=r["density"],tokens=r["tokens"]) for r in dl if r["arm"]=="skip"}
    gpath=OFF/"gold-spans.json.gz";gold=load(gpath)
    assert set(dec)==set(x)==set(dense)==set(gold)
    rows=[];seen=set();st=time.perf_counter()
    for p in files:
        for r in load(p):
            q=r["q"];t=r["t"]
            assert q not in seen and dec[q]["t"]==x[q]["t"]==t;seen.add(q)
            assert matched_pool(r)==x[q]["pool"]
            sel,toks=choose_skip(r)
            v=span_metrics_under_token_budget(tuple(RankedNodeRecord.model_validate(z) for z in sel),
                tuple(SourceSpan.model_validate(s) for s in gold[q]),2048)
            graph=dict(fs=int(v.full_support),coverage=v.coverage,density=v.density,tokens=toks)
            methods={a:"graph" if called else "dense" for a,called in dec[q]["call"].items()}
            methods.update(always_graph="graph",always_dense="dense")
            rows.append(dict(q=q,t=t,dense=dense[q],graph=graph,methods=methods))
    assert len(rows)==len(gold)==2000 and seen==set(x)
    t_diff=Counter(r["graph"]["fs"]-r["dense"]["fs"] for r in rows)
    ora=sorted(rows,key=lambda r:(-(r["graph"]["fs"]-r["dense"]["fs"]),hashstr("R20 oracle ties|"+r["q"])))
    for k in QUOTAS:
        n=sum(r["methods"]["gate"+str(k)]=="graph" for r in rows)
        for i,r in enumerate(ora):r["methods"]["oracle"+str(k)]="graph" if i<n else "dense"
    res={}
    for method in rows[0]["methods"]:
        calls=sum(r["methods"][method]=="graph" for r in rows)
        win_c=sum(r["methods"][method]=="graph" and r["graph"]["fs"]>r["dense"]["fs"] for r in rows)
        lose_c=sum(r["methods"][method]=="graph" and r["graph"]["fs"]<r["dense"]["fs"] for r in rows)
        res[method]=dict(calls=calls,rate=calls/len(rows),benefit_calls=win_c,harm_calls=lose_c,
             fs=sum(r[r["methods"][method]]["fs"] for r in rows),
             **{c:mean(r[r["methods"][method]][c] for r in rows) for c in FIELDS if c!="fs"})
    comp={}
    for k in QUOTAS:
        a="gate"+str(k)
        for b in ["always_graph","always_dense","margin"+str(k),"random"+str(k),"oracle"+str(k)]:
            comp[a+"-"+b]=contrast(rows,a,b)
    key="gate50-always_graph";lo=comp[key]["metric"]["fs"]["ci"][0]
    result=dict(n=len(rows),trajectories=len({r["t"] for r in rows}),oracles=dict(graph_only=t_diff[1],dense_only=t_diff[-1],equal=t_diff[0],
                unconstrained=sum(max(r["dense"]["fs"],r["graph"]["fs"]) for r in rows)),
        stats=res,paired=comp,primary=dict(rate=res["gate50"]["rate"],lower=lo,meets_rate=res["gate50"]["rate"]<=.60,
            meets_margin=lo>-.01,met=res["gate50"]["rate"]<=.60 and lo>-.01),seconds_score=time.perf_counter()-st,
        decision=sha(ROOT/(tag+"-decision-seal.json")),gold=sha(gpath),dense_test=sha(TR/"outcomes.json.gz"),
        graph_seal=sha(rank_seal),graph_ranks={p.name:sha(p) for p in files})
    put(ROOT/(tag+"-outcomes.json.gz"),rows);put(ROOT/(tag+"-results.json"),result)
    print(tag,result["primary"],{k:(v["calls"],v["fs"]) for k,v in res.items()})


if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("tag");a.add_argument("rank_dir",type=Path);a.add_argument("pattern");a.add_argument("rank_seal",type=Path)
    p=a.parse_args();main(p.tag,p.rank_dir,p.pattern,p.rank_seal)
