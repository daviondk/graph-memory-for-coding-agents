"""Clustered paired counts for observed support corrections. Resample whole trajectories."""
from pathlib import Path
import gzip,json
import numpy as np
D=Path(__file__).resolve().parent
def count(events):
    return [
        len(events),
        sum(e["before"]!=e["after"] for e in events),
        sum(e["before"]==e["first"]==e["second"]!=e["after"] for e in events),
        sum(e["x"]!=0 and e["y"]!=0 for e in events),
        sum(e["x"]!=0 or e["y"]!=0 for e in events),
        sum(e["total_cost"]>2048 for e in events),
        sum(len(set(e["before"])^set(e["after"])) for e in events),
        len({e["step"] for e in events}),
    ]
def metrics():
    data=json.loads(gzip.decompress((D/"packets.json.gz").read_bytes()))
    rng=np.random.default_rng(48019)
    boot=rng.integers(0,len(data),(10000,len(data)))
    out={}
    for cap in (1,4):
        rows=np.array([count([e for e in frame["events"] if e["cap"]==cap]) for frame in data.values()],dtype=np.int64)
        sums=rows[boot].sum(axis=1)
        totals=rows.sum(axis=0);nonempty=sums[:,0]>0
        measure=dict(zip(["pairs","changed","joint_only","both_effective","either_effective","budget_binds","sum_id_differences","groups"],map(int,totals)))
        measure["trajectories_eligible"]=int(np.count_nonzero(rows[:,0]))
        for label,idx in [("changed",1),("joint_only",2)]:
            measure[label+"_trajectories"]=int(np.count_nonzero(rows[:,idx]))
            measure[label+"_ci_percent"]=np.percentile(100*sums[nonempty,idx]/sums[nonempty,0],[2.5,97.5]).tolist() if totals[idx] else None
        out[str(cap)]=measure
    return dict(policies=out,trajectories=len(data),groups=sum(v["groups"] for v in data.values()),
                unmapped_candidates=sum(v["candidate_rows"]-v["items_with_sources"] for v in data.values()),
                excluded_pair_visits=sum(v["excluded_pair_visits"] for v in data.values()))
if __name__=="__main__":
    output=metrics();(D/"results.json").write_text(json.dumps(output,indent=2)+"\n",encoding="utf8");print(output)
