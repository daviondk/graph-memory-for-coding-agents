"""Paired trajectory bootstrap for native versus build-and-read latency."""
from collections import Counter
import gzip
import json
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent
def metrics():
    rows=json.loads(gzip.decompress((D/"timings.json.gz").read_bytes()))
    queries=sorted({r[0] for r in rows});pairs=sorted({r[1] for r in rows})
    assert len(queries)==40 and len(pairs)==1280 and len(rows)==5120
    assert set(Counter((r[0],r[1]) for r in rows).values())=={4}
    rng=np.random.default_rng(47072)
    times=rng.integers(0,len(queries),(10000,len(queries)))
    ci=lambda values: np.percentile(values,[2.5,97.5]).tolist()
    output={}
    for horizon in (1,2,4,8,16):
        samples=np.array([[cost+sum(mat[:horizon]),sum(native[:horizon])] for q,i,rep,cost,mat,native in rows],dtype=float)/1000
        totals=np.array([samples[[r[0]==q for r in rows]].sum(axis=0) for q in queries])
        sums=totals[times].sum(axis=1)
        pair_sum={i:0 for i in pairs}
        for _,i,_,cost,mat,native in rows:
            pair_sum[i]+=sum(native[:horizon])-cost-sum(mat[:horizon])
        wins=sum(delta>0 for delta in pair_sum.values())
        means=samples.mean(axis=0)
        output[str(horizon)]=dict(materialize_us=means[0],native_us=means[1],speedup=means[1]/means[0],
                    speedup_ci=ci(sums[:,1]/sums[:,0]),saved_us=means[1]-means[0],saved_ci=ci((sums[:,1]-sums[:,0])/len(rows)),pairs_faster=wins)
    return output
if __name__=="__main__":
    out=metrics()
    (D/"results.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf8")
    for h,r in out.items(): print(h,*(round(r[k],3) for k in ("materialize_us","native_us","speedup")),[round(v,3) for v in r["speedup_ci"]],r["pairs_faster"])
