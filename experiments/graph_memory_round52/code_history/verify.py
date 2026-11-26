"""Independent slow prefix reconstruction and report integrity check for all 995 forecasts."""
from collections import Counter
import numpy as np
from grade import paired
from prepare_data import HERE, read, save, sha

def replay_from_scratch(row, trace, model):
    prefix = [(k,p) for t,k,p in trace["events"] if t<=row["at"] and k!="B"]
    assert prefix[-1]==("E",row["path"])
    paths = [p for _,p in prefix]
    current = paths[-1]
    order = list(dict.fromkeys(reversed(paths)))
    pool = order[1:]
    assert pool==row["pool"]
    if not pool:
        assert all(v is None for v in row["pred"].values())
        return
    latest,counts = {},Counter(prefix)
    for i,(k,p) in enumerate(prefix):
        latest[p] = i,k
    switches = Counter((a,b) for a,b in zip(paths,paths[1:]) if a!=b)
    typed = Counter()
    for (left,source),(right,dest) in zip(prefix,prefix[1:]):
        if left=="E" and right=="R" and source!=dest:
            typed[source,dest]+=1
    assert len(typed)==row["typed_edges"] and len(switches)==row["switch_edges"]
    sat = lambda v:v/(1+v)
    scores={p:[] for p in ("sham","baseline","graph")}
    for rank,file in enumerate(pool,1):
        t,kind=latest[file]
        base = [1/(len(prefix)-t),1/rank,sat(counts["R",file]),sat(counts["E",file]),float(kind=="R"),
                float(trace["directory"][current]==trace["directory"][file])]
        common=sum(v*w for v,w in zip(base,model["beta"]))
        scores["baseline"].append(common)
        for mode,origin in (("graph",current),("sham",pool[0])):
            vals = [switches[origin,file],switches[file,origin],typed[origin,file]]
            scores[mode].append(common+sum(sat(v)*w for v,w in zip(vals,model["gamma"])))
    for k,option in scores.items():
        assert pool[option.index(max(option))]==row["pred"][k]

def main():
    test={t["issue"]:t for t in read(HERE/"test_trace.json.gz")}
    train_ids={t["issue"] for t in read(HERE/"train_trace.json.gz")}
    assert train_ids.isdisjoint(test)
    rows=read(HERE/"episodes.json.gz")
    model=read(HERE/"model.json")
    for r in rows:
        replay_from_scratch(r,test[r["issue"]],model)
    valid=[r for r in rows if r["status"]!="censored"]
    results=read(HERE/"results.json")
    assert results["paired_primary"]==paired(valid)
    extra={"retrospective_control_contrasts":{k:paired(valid,left="baseline",right=k) for k in ("mru","lfu","outgoing")},
           "independently_replayed":len(rows),"disjoint_issues":True,
           "status":"PASS","micro_oracle_hits":sum(r["status"] in ("same","reachable_other") for r in valid)}
    save("audit.json",extra)
    print("PASS",len(rows),len(valid),len(test),"inputs disjoint; scores, pools, counts and primary paired metrics reproduced")

if __name__=="__main__":
    main()

