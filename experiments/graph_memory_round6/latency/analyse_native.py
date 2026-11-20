import collections,hashlib,json,statistics
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent
def main():
    rows=[json.loads(l) for l in (D/"times_native.jsonl").read_text(encoding="utf8").splitlines()]
    assert len(rows)==len({r["key"] for r in rows})==186
    for r in rows:
        r["t"]=[statistics.median(r["us"][a])/1000 for a in ("archive","routed","lru")]
        assert all(len(x)==3 and min(x)>0 for x in r["us"].values())
    def summary(rr):
        vals=np.array([r["t"] for r in rr])
        return {"n":len(rr),"sum_ms":vals.sum(0).tolist(),"mean_ms":vals.mean(0).tolist(),"median_ms":np.median(vals,axis=0).tolist(),"p95_ms":np.percentile(vals,95,axis=0).tolist(),"fast_count":int(np.sum(vals[:,1]<vals[:,0])),"reduction":float(1-vals[:,1].sum()/vals[:,0].sum())}
    res={"all":summary(rows),"hot":summary([r for r in rows if r["hot"]]),"cold":summary([r for r in rows if not r["hot"]])}
    rng=np.random.default_rng(6728)
    for level in ("id","repo"):
        groups=collections.defaultdict(list)
        for r in rows:groups[r[level]].append(r["t"])
        mat=np.stack([np.sum(x,axis=0) for x in groups.values()])
        totals=mat[rng.integers(0,len(mat),(10000,len(mat)))].sum(1)
        effects=1-totals[:,1]/totals[:,0]
        res[level]={"n":len(mat),"reduction_ci":np.percentile(effects,[2.5,97.5]).tolist()}
    res["sha256"]=hashlib.sha256((D/"times_native.jsonl").read_bytes()).hexdigest()
    (D/"native_results.json").write_text(json.dumps(res,indent=1),encoding="utf8");print(json.dumps(res))
if __name__=="__main__":main()


