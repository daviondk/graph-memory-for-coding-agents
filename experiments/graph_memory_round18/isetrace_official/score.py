"""Seal source-only predictions before scoring, check every arm with the official scorer and a second interval implementation."""
from pathlib import Path
from collections import Counter,defaultdict
from statistics import mean
import dataclasses
import gzip
import json
import math
import sys
import numpy as np
import rank
from discover import ROOT, BASE, load, write, pilot
from verify_records import metrics as independent_metric

def datasets():
    rows=load("cohort.json")
    assert len(set(r["query_id"] for r in rows))==len(rows)
    return rows
def seal_predictions():
    plan=pilot.sha(ROOT/"ranking-plan.json")
    tids=sorted(set(r["trajectory_id"] for r in datasets()))
    by=defaultdict(list)
    for t in tids:
        f=rank.state_file(t)
        assert rank.checked(f,plan)
        rec=json.loads(gzip.decompress(f.read_bytes()))
        assert rec["trajectory_id"]==t
        by[rec["shard"]].append((t,f))
    names={}
    for i,files in sorted(by.items()):
        name=f"forecasts-shard-{i}.jsonl.gz";target=ROOT/name;tmp=target.with_suffix(".tmp")
        with tmp.open("wb") as binary,gzip.GzipFile(filename="",fileobj=binary,mode="wb",compresslevel=4,mtime=0) as out:
            for t,f in files:
                with gzip.open(f,"rb") as src:out.write(src.read())
        if target.exists():
            assert pilot.sha(tmp)==pilot.sha(target)
            tmp.unlink()
        else:tmp.replace(target)
        names[name]=pilot.sha(target)
    assert set(by)==set(range(8))
    write("forecast-lock.json",dict(plan=plan,forecasts=names,trajectories=len(tids)))
def exact(w,l):
    n=w+l
    return min(1.,2*sum(math.comb(n,j) for j in range(1+min(w,l)))/2**n)
def compare(test,ref):
    assert set(test)==set(ref)
    groups=defaultdict(list);win=lose=0
    for q,r in test.items():
        d=r["full_support"]-ref[q]["full_support"]
        groups[r["t"]].append(d);win+=int(d>0);lose+=int(d<0)
    totals=np.array([sum(v) for k,v in sorted(groups.items())]);sizes=np.array([len(v) for k,v in sorted(groups.items())])
    rng=np.random.default_rng(13);sims=[]
    for _ in range(40):
        idx=rng.integers(0,len(groups),size=(250,len(groups)))
        sims.extend(totals[idx].sum(axis=1)/sizes[idx].sum(axis=1))
    return {"delta":float(totals.sum()/sizes.sum()),"full_wins":win,"full_losses":lose,"ties":len(test)-win-lose,
            "trajectory_bootstrap_ci95":np.quantile(sims,[.025,.975]).tolist(),"query_exact_mcnemar_p_descriptive":exact(win,lose)}
def evaluate():
    seal=load("forecast-lock.json")
    assert seal["plan"]==pilot.sha(ROOT/"ranking-plan.json")
    cohort={r["query_id"]:r for r in datasets()}
    gold={q:tuple(pilot.SourceSpan.model_validate(g) for g in spans) for q,spans in load("gold-spans.json.gz").items()}
    assert set(gold)==set(cohort)
    observed=[];reconstructed=set()
    for file,h in seal["forecasts"].items():
        assert pilot.sha(ROOT/file)==h
        for rec in streamgz(ROOT/file):
            t=rec["trajectory_id"]
            for q,views in rec["queries"].items():
                assert q not in reconstructed and cohort[q]["trajectory_id"]==t
                reconstructed.add(q)
                g=gold[q];gjson=[v.model_dump() for v in g]
                for view,v in views.items():
                    rr=tuple(pilot.RankedNodeRecord.model_validate(r) for r in v["ranked"]);pool={n.node_id:n for n in rr}
                    assert len(pool)==len(rr)
                    if v["partial"]:
                        node=pilot.RankedNodeRecord.model_validate(v["partial"]);assert node.node_id not in pool
                        pool[node.node_id]=node
                    for pol,ids in v["arms"].items():
                        nodes=tuple(pool[k] for k in ids);cost=sum(n.token_count for n in nodes)
                        assert len(ids)==len(set(ids)) and cost<=rank.B
                        res=pilot.span_metrics_under_token_budget(nodes,g,rank.B)
                        if pol=="prefix":assert res==pilot.span_metrics_under_token_budget(rr,g,rank.B)
                        check=independent_metric(gjson,[n.model_dump() for n in nodes])
                        assert all(abs(val-getattr(res,field))<1e-12 for val,field in zip(check,("coverage","density","full_support"),strict=True))
                        observed.append(dict(q=q,t=t,memory_mode=cohort[q]["memory_mode"],shard=rec["shard"],view=view,arm=pol,
                                            tokens=cost,nodes=len(nodes),**dataclasses.asdict(res)))
    assert reconstructed==set(cohort)
    write("outcomes.json.gz",observed)
    old=set()
    for f in (BASE/"cohort.json",BASE/"replication/cohort.json"):
        old.update(json.loads(f.read_bytes())["selected"])
    assert len(old)==128
    summary={}
    for label,rows in (("all",observed),("no_previous_trajectories",[r for r in observed if r["t"] not in old])):
        items=defaultdict(dict)
        for r in rows:items[r["view"]+"/"+r["arm"]][r["q"]]=r
        metrics={}
        for arm,rs in items.items():
            arr=list(rs.values())
            metrics[arm]={"n":len(rs),"full_count":int(sum(x["full_support"] for x in arr)),
                          **{m:mean(x[m] for x in arr) for m in ("coverage","density","full_support","f1","nodes","tokens")}}
        pairs={}
        for v in ("flat","provenance"):
            for a,c in [("skip","prefix"),("clip","prefix"),("value","prefix"),("value","skip"),("skip","clip"),("value","clip")]+([("related","skip"),("related","value")] if v=="provenance" else []):
                pairs[f"{v}/{a}-{c}"]=compare(items[f"{v}/{a}"],items[f"{v}/{c}"])
        summary[label]={"metrics":metrics,"paired":pairs,"unique_trajectories":len({r["t"] for r in rows})}
    fs=summary["all"]["metrics"]["flat/prefix"]
    summary["official_calibration"]={"shape_match":load("split-verification.json")["official_signature_match"],"expected_n":2000,"expected_bm25_fs_count":759,"observed_n":fs["n"],"observed_count":fs["full_count"],"matches":fs["n"]==2000 and fs["full_count"]==759}
    write("results.json",summary)
    print(summary["official_calibration"],flush=True)
    print({k:(v["full_count"],round(v["tokens"],1)) for k,v in summary["all"]["metrics"].items()},flush=True)
def streamgz(path):
    with gzip.open(path,"rb") as f:
        for l in f:yield json.loads(l)
if __name__=="__main__":seal_predictions();evaluate()
