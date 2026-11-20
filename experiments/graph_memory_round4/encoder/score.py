"""Post-lock grading. Scores never feed back into the independent encoder run."""
from collections import defaultdict
import numpy as np
import pyarrow.parquet as pq
from common_run import D, R, cases, hashfile, load, now, readgz, save, writegz

assert hashfile(D/"predictions.jsonl.gz")==load(D/"prediction_lock.json")["pred_sha"]
assert hashfile(R/"strict_java.pred.jsonl.gz")==load(R/"strict_graph_lock.json")["sha256"]
assert hashfile(R/"assoc.pred.jsonl.gz")==load(R/"assoc_prediction_lock.json")["sha256"]

def group_stats(records, compare):
    arrays = {name:np.asarray([r[1][name] for r in records]) for name in records[0][1]}
    def summary(v):
        return dict(top1=int((v==1).sum()),top3=int((v<=3).sum()),top5=int((v<=5).sum()),mrr=float((1/v).mean()),meanrank=float(v.mean()))
    names, group = np.unique([r[0] for r in records],return_inverse=True)
    n = np.bincount(group)
    draws = np.random.default_rng(20261118).integers(len(n),size=(5000,len(n)))
    answers = {}
    for a,b in compare:
        va, vb = arrays[a],arrays[b]
        dp=(va==1).astype(int)-(vb==1).astype(int)
        drr=1/va-1/vb
        def conf(v):
            sums = np.bincount(group,weights=v)
            distribution=sums[draws].sum(axis=1)/n[draws].sum(axis=1)
            return {"delta":float(v.mean()),"lo":float(np.quantile(distribution,.025)),"hi":float(np.quantile(distribution,.975))}
        answers[a+"-"+b]=dict(top1=conf(dp),mrr=conf(drr),win=int((dp>0).sum()),lost=int((dp<0).sum()),improved_rank=int((va<vb).sum()),worse_rank=int((va>vb).sum()))
    return {"n":len(records),"projects":len(names),"stats":{a:summary(v) for a,v in arrays.items()},"contrasts":answers}

rankings = defaultdict(dict)
projects = {}
lex = {}
for p in readgz(D/"predictions.jsonl.gz"):
    tag = p["query"]
    key = p["panel"],p["idx"],int(tag.rstrip("a"))
    rankings[key]["unix_author" if tag.endswith("a") else "unix"] = p["rank"]
    projects[key] = p["project"]
for arms in rankings.values():
    arms.setdefault("unix_author",arms["unix"])
assert len(rankings)==640
for panel,i,k,project,size,h,e,arms in readgz(R/"strict_java.pred.jsonl.gz"):
    key = panel,i,k
    if key in rankings:
        assert projects[key]==project
        for name in ("graph","owner","publisher_bm25"):
            rankings[key][name]=arms[name]
for stage,panel,i,project,h,sz,arms in readgz(R/"assoc.pred.jsonl.gz"):
    if stage=="novel_java" and (panel,i,3) in rankings:
        assert projects[panel,i,3]==project
        rankings[panel,i,3]["assoc"]=arms["learned"]
for manifest in load(R/"paired_decision_lock.json")["runs"]:
    path=R/("paired_"+manifest["config"]+".json")
    assert hashfile(path)==manifest["output_sha"]
    for panel,i,k,returned,order in load(path):
        rankings[panel,i,k]["semlith"]=order
gold={}
for path, panel, mapping in cases():
    vals=pq.read_table(path, columns=["gold_snippet_index"]).column(0)
    for j,idx in mapping.items():
        gold[panel,idx]=vals[j].as_py()
assert len(gold)==320
rows=[]
for (panel,i,k),arms in sorted(rankings.items()):
    assert {"unix","unix_author","graph","owner","publisher_bm25","semlith"} <= set(arms)
    # Association model ran only on the overlap with a prior 1000-case panel.
    candidate_ids=sorted(arms["unix"])
    assert candidate_ids==list(range(len(candidate_ids))) and all(sorted(r)==candidate_ids for r in arms.values())
    correct=gold[panel,i]
    rows.append(dict(panel=panel,idx=i,keep=k,project=projects[panel,i,k],gold=correct,ranks={a:order.index(correct)+1 for a,order in arms.items()}))
writegz(D/"scores.jsonl.gz",rows)
allstats = {}
strata = {}
for k in (3,10):
    rr = [r for r in rows if r["keep"]==k]
    rr = [dict(r,ranks={a:v for a,v in r["ranks"].items() if a != "assoc"}) for r in rr]
    names = list(rr[0]["ranks"])
    contrasts=[(a,"unix") for a in names if a!="unix"]
    allstats[str(k)]=group_stats([(r["project"],r["ranks"]) for r in rr],contrasts)
    for stratum in sorted({r["panel"] for r in rr}|{"easy", "hard"}):
        vals = [r for r in rr if r["panel"]==stratum or r["panel"].endswith("_"+stratum)]
        strata[str(k)+"/"+stratum]=group_stats([(r["project"],r["ranks"]) for r in vals],[])
look={(r["panel"],r["idx"],r["keep"]):r for r in rows}
paired=[]
for (p,i,k),r in look.items():
    if k==3:
        paired.append((r["project"],{"three":r["ranks"]["unix"],"ten":look[p,i,10]["ranks"]["unix"]}))
partial=[(r["project"],r["ranks"]) for r in rows if "assoc" in r["ranks"]]
assert len(partial)==271
save("results.json",dict(utc=now(),association_overlap=group_stats(partial,[("assoc","unix"),("graph","unix")]),all=allstats,strata=strata,long_minus_short=group_stats(paired,[("ten","three")]),metrics_sha=hashfile(D/"scores.jsonl.gz"),n=320,seed=20261118,replicates=5000))
print({k:r["stats"] for k,r in allstats.items()})

