"""Recompute released outcome joins, clustered uncertainty, incomplete runs and costs using stdlib."""
from collections import Counter,defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean, median

ROOT=Path(__file__).resolve().parent
VIEWS=["repo_only","raw_trace","summary_notes","structured_notes","policy"]
def readrows(n):
    with (ROOT/n).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def quantile(v,p):
    a=sorted(v);r=(len(a)-1)*p;i=int(r)
    return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(r-i)
def result(x, k):
    if k=="success":return int(x["official_known"]=="1" and x["official_resolved"]=="1")
    if not x[k]:return None
    return float(x[k])
def summary(rs):
    ans={"n":len(rs),"instances":len(set(r["instance"] for r in rs)),"arms":{}}
    for v in VIEWS:
        ds=[r[v] for r in rs]
        ok=sum(result(d,"success") for d in ds);known=sum(d["official_known"]=="1" for d in ds)
        d={"official_solved":ok,"official_known":known,"official_unknown":len(ds)-known,
           "run_errors":sum(y["run_error"]=="1" for y in ds),"validation_passed":sum(y["passed"]=="1" for y in ds)}
        for keep in ["prompt_tokens","completion_tokens","agent_events","agent_seconds"]:
            nums=[result(y,keep) for y in ds if result(y,keep) is not None]
            d[keep]={"mean":mean(nums) if nums else None,"median":median(nums) if nums else None,
                     "n":len(nums),"zeros":sum(n==0 for n in nums)}
        ans["arms"][v]=d
    return ans
def contrasts(rs,layer="all",bs=False,other="structured_notes"):
    grouped=defaultdict(list)
    for row in rs:
        y,x=row["policy"],row[other]
        if layer=="known" and (y["official_known"]!="1" or x["official_known"]!="1"):continue
        grouped[row["instance"]].append(result(y,"success")-result(x,"success"))
    v=[a for task in grouped.values() for a in task];n=len(v);w=v.count(1);l=v.count(-1)
    if not n:return {"n":0}
    cp=[(sum(arr),len(arr)) for arr in grouped.values()]
    ans={"n":n,"targets":len(cp),"wins":w,"losses":l,"ties":n-w-l,
         "delta_pp":100*mean(v),"delta_equal_task_pp":100*mean(s/n for s,n in cp),
         "p_descriptive":min(1.,2*sum(math.comb(w+l,k) for k in range(min(w,l)+1))/2**(w+l))}
    if bs:
        rng=random.Random(16112026);samps=[]
        for _ in range(10000):
            sample=rng.choices(cp,k=len(cp));samps.append(100*sum(s for s,n in sample)/sum(n for s,n in sample))
        ans["ci95_pp"]=[quantile(samps,.025),quantile(samps,.975)]
    for k in ["prompt_tokens","agent_events","agent_seconds"]:
        delta=[]
        for r in rs:
            a=result(r["policy"],k);b=result(r[other],k)
            if layer=="known" and (r["policy"]["official_known"]!="1" or r[other]["official_known"]!="1"):continue
            if a is not None and b is not None:delta.append(a-b)
        ans[k]={"n_pairs":len(delta),"mean_paired_delta":mean(delta),"median_paired_delta":median(delta)}
    return ans
def compute():
    a=readrows("assignments.csv"); outcomes={r["run_id"]:r for r in readrows("arm_outcomes.csv")}
    assert len(a)==1530 and len(outcomes)==6120
    joined=[]
    for r in a:
        d={k:r[k] for k in ["instance","pred","succ","checkpoint","kind","subset"]}
        assert r["policy"]==("raw_trace" if r["kind"]=="post_failed_repair_edit" else "structured_notes")
        d.update({v:outcomes[r[v]] for v in VIEWS[:-1]});d["policy"]=d[r["policy"]];joined.append(d)
    ds={"all":joined}
    for key in ["kind","pred","succ","subset"]:
        for val in sorted({r[key] for r in joined}):ds[key+"/"+val]=[r for r in joined if r[key]==val]
    result_={k:{**summary(g),"policy_vs_structured_primary":contrasts(g,bs=(k=="all" or k=="kind/post_failed_repair_edit")),
                "known_sensitivity":contrasts(g,layer="known",bs=k=="all"),"policy_vs_raw_secondary":contrasts(g,other="raw_trace",bs=k=="all")} for k,g in ds.items()}
    status=Counter((d["backend"],d["official_known"],d["passed"],d["official_resolved"]) for d in outcomes.values())
    return {"source_rows":6120,"conditions":result_,"raw_grade_combinations":[{"backend":k[0],"known":k[1],"passed":k[2],"official_resolved":k[3],"n":n} for k,n in status.items()]}
if __name__=="__main__":
    r=compute();(ROOT/"results.json").write_text(json.dumps(r,indent=1),encoding="utf-8")
    print(r["conditions"]["all"]["policy_vs_structured_primary"])
    print(r["raw_grade_combinations"])
    for k,v in r["conditions"]["all"]["arms"].items(): print(k,v["official_solved"],v["official_known"],v["prompt_tokens"],v["agent_events"])

