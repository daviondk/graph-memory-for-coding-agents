"""Unseal external labels only after the completed ranking has been frozen."""
import collections
import gzip
import json
import random
import statistics
from prepare import ROOT,hashbytes,load,save
from predict import locate
ARMS=("address","minlex","rarelex","shape","mixed","full")
def aggregate(group):
    result={}
    for arm in ARMS:
        ranks=[r["rank"][arm] for r in group]
        result[arm]=dict(top1=ranks.count(1),top3=sum(0<x<=3 for x in ranks),mrr=sum(1/x for x in ranks if x)/max(1,len(ranks)))
    return result
def confident(scores):
    v=sorted(scores,reverse=True)
    return bool(v and v[0]>=2 and v[0]-(v[1] if len(v)>1 else 0)>=2)
def main():
    for f,h in load("prediction-lock.json").items():assert hashbytes((ROOT/f).read_bytes())==h
    a=load("source-lock.json")
    for f,h in a["hashes"].items():assert hashbytes((ROOT/f).read_bytes())==h
    labels=load("labels.json")
    pools=json.loads(gzip.decompress((ROOT/"pools.json.gz").read_bytes()))
    rows=[];diagn=collections.Counter();payload=collections.defaultdict(list)
    for ln in gzip.decompress((ROOT/"rankings.jsonl.gz").read_bytes()).splitlines():
        r=json.loads(ln);l=labels[r["case"]]
        p=pools[r["commit"]]["candidates"]
        cand=[dict(path=v[0],qual=v[1],line=v[2],name=v[1].split(".")[-1]) for v in p]
        ix=locate(cand,l["name"],l["scope"])
        target=ix[0] if len(ix)==1 else None
        ranks={k:(r["rankings"][k].index(target)+1 if target is not None else 0) for k in ARMS}
        v=r["mixed_scores"]
        ok=confident(v)
        diagn["answered"]+=int(ok);diagn["answered_incorrect"]+=int(ok and ranks["mixed"]!=1)
        if target is not None:
            diagn["ablated_n"]+=1
            diagn["confident_with_target_removed"]+=int(confident(v[:target]+v[target+1:]))
        rows.append(dict(case=r["case"],project=r["project"],commit=r["commit"],kind=l["kind"],n_candidates=len(p),
                 same_path=(r["origin"][0]==p[target][0] if target is not None else None),gold_matches=len(ix),rank=ranks,
                 confident=ok,gold=p[target] if target is not None else None,origin=r["origin"]))
        for k,val in r["bytes"].items():payload[k].append(val)
    groups=collections.defaultdict(list)
    for i in rows:groups[i["commit"]].append(i)
    pair=[(len(g),sum((r["rank"]["mixed"]==1)-(r["rank"]["rarelex"]==1) for r in g)) for g in groups.values()]
    rng=random.Random(81173);dist=[]
    for i in range(10000):
        sample=rng.choices(pair,k=len(pair));dist.append(sum(x[1] for x in sample)/sum(x[0] for x in sample))
    dist.sort()
    resolved=[r for r in rows if r["gold_matches"]==1]
    agg=aggregate(rows)
    result=dict(n=len(rows),n_commits=len(groups),n_resolved=len(resolved),arms=agg,resolved_arms=aggregate(resolved),
            primary_effect=(agg["mixed"]["top1"]-agg["rarelex"]["top1"])/len(rows),ci=[dist[249],dist[9749]],
            source_excluded=a["excluded"],unresolved_old=len(load("skips.json")),confidence=diagn,
            identified_candidates=dict(min=min(r["n_candidates"] for r in rows),median=statistics.median(r["n_candidates"] for r in rows),max=max(r["n_candidates"] for r in rows)),
            bytes={k:dict(mean=statistics.mean(vals),median=statistics.median(vals)) for k,vals in payload.items()})
    for key in ("kind","project","same_path"):
        result[key]={str(x):dict(n=len(g),top1={arm:res["top1"] for arm,res in aggregate(g).items()}) for x in dict.fromkeys(r[key] for r in rows) for g in [[r for r in rows if r[key]==x]]}
    save("outcomes.json",rows);save("results.json",result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("kind","project","same_path","resolved_arms")},indent=2))
if __name__=="__main__":main()
