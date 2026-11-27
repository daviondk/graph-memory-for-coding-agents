"""Verify exact marginal values against two independent physical SQLite replays."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from pathlib import Path
import sys

from value import bracket, gain, tiny

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"restart_transfer"))
from run_transfer import ARMS, count, load, prepare, save, source
from audit import chosen, width
from bench_restart import panels


def components(ops):
    events=[op[3] for op in ops if op[0]=="w"]
    fence=len(events)//2
    pre=defaultdict(set)
    for j,ids in enumerate(events[:fence]):
        for f in ids:pre[f].add(j)
    eligible=chosen(events[:fence],None,"recent")[0]
    size=[sum(map(width,paths)) for paths in events]
    costs={j:width(j)+width(size[j])+size[j] for j in eligible}
    reads=Counter()
    paid=Counter()
    current=defaultdict(list)
    late=defaultdict(list)
    seen=set()
    n=0
    for op in ops:
        if op[0]=="w":
            _,j,_,ids=op
            for f in ids:
                current[f].append(j)
                if j>=fence:late[f].append(j)
            n+=1
        elif n>=fence:
            f=op[1]
            reads[f]+=1
            if f in seen and pre[f] and pre[f]<=eligible:
                hot={j for history in late.values() for j in history[-8:]}
                if all(j in hot for j in late[f]):
                    paid[f]+=sum(map(width,current[f]))
            seen.add(f)
    values={j:size[j]*sum(reads[f] for f in events[j]) for j in eligible}
    bonuses=Counter()
    for f,v in paid.items():
        bonuses[frozenset(pre[f])]+=v
    return events[:fence],costs,values,bonuses


def case(ops,actual):
    events,costs,values,bonuses=components(ops)
    arms={}
    controls=[]
    for name,(policy,cap) in ARMS.items():
        selected,_,_=chosen(events,cap,policy)
        body,posting=gain(selected,values,bonuses)
        assert (body,posting)==(actual["cold"]["body_bytes"]-actual[name]["body_bytes"],
                                actual["cold"]["posting_bytes"]-actual[name]["posting_bytes"])
        arms[name]=dict(body=body,posting=posting)
        if cap==1024:controls.append(selected)
    lo,hi,subset=bracket(costs,values,bonuses,1024-40,controls)
    return dict(arms=arms,lo=lo,hi=hi,chosen=sorted(subset),used=sum(costs[j] for j in subset)+40,
                eligible=len(values),groups=len(bonuses),bonus_value=sum(bonuses.values()),
                multi_groups=sum(len(s)>1 for s in bonuses),post=actual["cold"]["post"])


def run():
    result={}
    raw=load(HERE.parent/"restart/runs.json.gz")["runs"]
    old=panels()
    for p in ("B","long"):
        for repo,rows in old[p].items():
            arm={s["method"]:count(s["stats"],s["queries"]) for s in raw
                 if s["panel"]==p and s["project"]==repo and s["rep"]==0}
            ops,_=prepare(rows,p)
            result["original/"+p+"/"+repo]=case(ops,arm)
    extra=load(HERE.parent/"restart_transfer/runs.json.gz")["projects"]
    for name in ("replication","seed_pair"):
        projects,_=source(name)
        for repo,rows in projects.items():
            for p in ("B","long"):
                meters=extra[name+"/"+repo]["workloads"][p]["arms"]
                ops,_=prepare(rows,p)
                result[name+"/"+p+"/"+repo]=case(ops,{m:v["summary"] for m,v in meters.items()})
    totals={}
    for key,data in result.items():
        group=key.split("/")[:2]
        row=totals.setdefault("/".join(group),Counter())
        row.update({k:data[k] for k in ("lo","hi","post","groups","multi_groups")})
        for name,v in data["arms"].items():
            for k,amount in v.items():row[name+"_"+k]+=amount
    return dict(cases=result,groups=totals,small=tiny())


if __name__=="__main__":
    ap=ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    result=run()
    path=HERE/"results.json"
    if args.verify:assert result==load(path)
    else:save(path,result)
    print(result["small"])
    for g,s in result["groups"].items():
        print(g, s["post"],s["demand1024_body"],s["demand1024_posting"],s["lo"],s["hi"])
