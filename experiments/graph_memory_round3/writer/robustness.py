"""Descriptive sensitivity to repeated edits, long trajectories, generator tags and prior actor."""
import sys,collections,re
from pathlib import Path
from replay import D,DATA,old,rows,save
sys.path.insert(0,str(D))
from score import stats
from pipeline import future
import numpy as np
def metric(group):
    a=np.array([x[2] for x in group]);b=np.array([x[3] for x in group]);grp=[x[0].split(".")[0] for x in group]
    out=stats(a,b,grp);out.pop("project_sums");out.update(n=len(a),repos=len(set(grp)),typed=int(a.sum()),point=int(b.sum()));return out
def panel(folder,f):
    src={x["instance"]:x for k in range(8) for x in rows(folder/f"source_{k}.jsonl.gz")};data=[]
    for i,t,n,m in rows(D/f):
        r=src[i];q=future(r["events"],t);assert q and q[2]
        tag="pr" if re.search(r"(?:^|\.)pr_\d+$",i) else "lm" if ".lm_" in i else "procedural" if ".func_" in i else "combined_or_other"
        data.append([i,t,m["typed@4096"][0],m["point@4096"][0],(i,q[0],old.e.sha(q[1])),tag,r["model"]])
    data.sort(key=lambda x:(x[0],x[1]));unique={};first={};by=collections.defaultdict(list)
    for x in data:
        unique.setdefault(x[4],x);first.setdefault(x[0],x);by[x[0]].append(x)
    by_task=np.array([np.mean([x[2]-x[3] for x in v]) for v in by.values()]);names=[i.split(".")[0] for i in by]
    balanced=stats(by_task,np.zeros(len(by_task)),names);balanced.pop("project_sums")
    return {"all":metric(data),"distinct_target_in_trajectory":metric(list(unique.values())),"first_edit_per_trajectory":metric(list(first.values())),"task_balanced":balanced,
        "generator_tag":{k:metric([x for x in data if x[5]==k]) for k in sorted({x[5] for x in data})},"original_actor":{k:metric([x for x in data if x[6]==k]) for k in sorted({x[6] for x in data})}}
if __name__=="__main__":save(D/"robustness.json",{"primary":panel(DATA,"per_cut.jsonl.gz"),"replication":panel(DATA/"replication","opt_scored.jsonl.gz")})
