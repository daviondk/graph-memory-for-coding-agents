import csv
import gzip
import json
import os
import random
from collections import Counter,defaultdict
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from replay import HERE,ARMS


def records(name):
    with gzip.open(HERE/name,"rt",encoding="utf8") as f:
        yield from map(json.loads,f)


def bootstrap(groups):
    keys=sorted(groups)
    rng=random.Random(20261116)
    w=np.zeros((10000,len(keys)),dtype=np.int64)
    for i in range(len(w)):
        w[i]=np.bincount(rng.choices(range(len(keys)),k=len(keys)),minlength=len(keys))
    den=np.array([groups[k]["n"] for k in keys])
    ns=w @ den; keep=ns>0
    out={}
    for a,b in (("selective","flush"),("write_through","selective"),("selective","ttl1"),("selective","lru")):
        d={}
        for m in ("correct","stale","unknown"):
            xs=np.array([groups[k][a+"_"+m]-groups[k][b+"_"+m] for k in keys])
            rates=(w@xs)[keep]*1000/ns[keep]
            d[m]={"count":int(xs.sum()),"per1000":float(xs.sum()*1000/den.sum()),
                  "ci95":np.quantile(rates,[.025,.975]).tolist()}
        out[a+"-"+b]=d
    return out


def main():
    repo=defaultdict(Counter);trace=defaultdict(Counter)
    metrics={a:Counter() for a in ARMS};pop=Counter();peak=Counter()
    coverage=Counter()
    for h in records("histories.jsonl.gz"):
        pop.update(h["counts"])
        key=h.get("repo_proxy") or "unresolved"
        coverage[key]+=1
        for g in (repo[key],trace[h["sid"]]):
            g["n"]+=h["counts"].get("eligible",0)
            for a,m in h["arms"].items():
                for k in ("correct","stale","unknown","miss"):
                    g[a+"_"+k]+=m.get(k,0)
        for a,m in h["arms"].items():
            metrics[a].update({k:v for k,v in m.items() if k!="peak"})
            peak[a]=max(peak[a],m["peak"])
    seen={};audit=defaultdict(Counter);outcomes=defaultdict(Counter)
    for q in records("queries.jsonl.gz"):
        for a,h in zip(ARMS,q["arms"]):
            state="miss"
            if h:
                b,slot,state,edits,pred=h
                prev=seen[q["sid"],b,slot]
                assert b<q["b"] and prev["admitted"] and prev["key"]==q["key"]
                if not edits:
                    assert pred==prev["sha256"]
                else:
                    assert a=="write_through" and prev["roundtrip_full"] and b<min(edits)<=max(edits)<q["b"]
                truth="unknown" if q["actual"]=="unknown" else "correct" if q["actual"]=="success" and q["sha256"]==pred else "stale"
                assert state==truth
            audit[a][state]+=1
            outcomes[a][q["actual"]+"_"+state]+=1
        seen[q["sid"],q["b"],q["slot"]]=q
    assert len(seen)==pop["eligible"]
    for a in ARMS:
        assert all(metrics[a][k]==v for k,v in audit[a].items())
        metrics[a]["peak_bytes"]=peak[a]
        metrics[a]["mean_end_bytes"]=metrics[a]["sum_end_bytes"]/pop["batches"]
    result={"population":pop,"traces":len(trace),"traces_with_read":sum(bool(g["n"]) for g in trace.values()),
            "repo_proxy_histories":coverage,"policies":metrics,"outcomes_by_actual":outcomes,
            "bootstrap_repo":bootstrap(repo),"bootstrap_trace":bootstrap(trace),"numpy":np.__version__}
    (HERE/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    for name,groups in (("repositories",repo),("trajectories",trace)):
        keys=sorted(set().union(*(c.keys() for c in groups.values())))
        with (HERE/(name+".csv")).open("w",encoding="utf8",newline="") as f:
            w=csv.writer(f);w.writerow([name,*keys])
            for g in sorted(groups):w.writerow([g,*(groups[g][k] for k in keys)])
    print(pop)
    print(dict(audit))


if __name__=="__main__":
    main()
