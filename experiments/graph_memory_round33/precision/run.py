"""Replay five sealed E5 rankings and independently check every ordered prefix."""
import gzip,hashlib,json,struct
from pathlib import Path
from collections import defaultdict
from statistics import mean
import numpy as np
from layers import Index,exact,prefix
HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1];FIX=WORK/"graph_memory_round22/threshold_read";FIVE=WORK/"graph_memory_round21/five_seed"
SEEDS=(13,17,29,37,41);MODES=("b4","b4_b8","b8","fp16")
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def put(p,data):
    b=(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def hashfile(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def calibration(s):
    return (WORK/"graph_memory_round20/factor_reader/hash64-weights.json" if s==13 else FIVE/f"seed-{s}/calibration.json")
def inputs():
    files=[FIX/f"fixture-{i}.json.gz" for i in range(8)]
    files.extend(FIVE/f"seed-{s}/picks-{i}.json.gz" for s in SEEDS for i in range(8))
    files.extend(calibration(s) for s in SEEDS)
    return {p.relative_to(WORK).as_posix():hashfile(p) for p in files}
def signal_native(model,n):
    r=np.arange(1,n+1);x=np.column_stack((-np.log(r),1/r,(n-r)/max(1,n-1)))
    return x@np.array(model["coef"])+model["intercept"]
def histories(shard):
    ranks={s:{v['q']:v for v in read(FIVE/f"seed-{s}/picks-{shard}.json.gz")} for s in SEEDS}
    cal={s:read(calibration(s))["rank"] for s in SEEDS}
    for group in read(FIX/f"fixture-{shard}.json.gz"):
        index=Index(group["prior"]);cost=np.array(group["costs"]);n=len(cost)
        def requests():
            for request in group["queries"]:
                q=request["q"];canonical=np.array(request["order"])
                for s in SEEDS:
                    ref=ranks[s][q];order=canonical[ref["dense"]];signal=signal_native(cal[s],n)
                    target=prefix(canonical[ref["factor"]],cost)
                    if s==13:assert request["expected"]["prefix"]==target
                    yield q,s,order,signal,target
        yield group["t"],index,cost,requests()
def sizes(index):
    n=len(index.raw);unique=len(set(index.raw));bits=(unique-1).bit_length()
    return {"b4":16+len(index.high),"b8":16+n,"fp16":2*n,"fp64":8*n,"dictionary":8*unique+(bits*n+7)//8+4,"dict_values":unique,"n":n}
def main():
    put(HERE/"plan.json",{"inputs":inputs(),"protocol":hashfile(HERE/"PROTOCOL_RU.md"),"code":{p:hashfile(HERE/p) for p in ["layers.py","run.py"]}})
    storage={};out={}
    for shard in range(8):
        for t,index,cost,requests in histories(shard):
            storage[t]=sizes(index)
            for q,s,order,signal,target in requests:
                native=order[np.argsort(-(signal+index.raw[order]),kind="stable")]
                assert target==prefix(native,cost),(s,q)
                modes={}
                for m in MODES:
                    got,reads=exact(m,index,order,signal,cost,index.low.__getitem__,index.raw.__getitem__)
                    assert got==target,(s,q,m)
                    lo,hi=index.interval(m,order)
                    approx=order[np.argsort(-(signal+.5*(lo+hi)),kind="stable")]
                    got_approx=prefix(approx,cost)
                    modes[m]=[reads[0],reads[1],int(got_approx==target),int(set(got_approx)==set(target))]
                out.setdefault(q,{"t":t,"seeds":{}})["seeds"][str(s)]=modes
    assert len(storage)==1207 and len(out)==2000
    put(HERE/"rows.json.gz",out);put(HERE/"storage.json.gz",storage)
    items=[row for v in out.values() for row in v["seeds"].values()]
    stats={}
    for m in MODES:
        a=np.asarray([r[m] for r in items])
        stats[m]={"requests":len(a),"low_bytes":int(a[:,0].sum()),"exact_values":int(a[:,1].sum()),
                  "refine_bytes":int((a[:,0]+8*a[:,1]).sum()),"no_external_pct":100*np.mean(a[:,0]+a[:,1]==0),
                  "approx_ordered":int(a[:,2].sum()),"approx_set":int(a[:,3].sum())}
    put(HERE/"results.json",{"n":len(out),"groups":len(storage),"methods":stats,"sizes":{m:sum(v[m] for v in storage.values()) for m in next(iter(storage.values()))},
        "rows":hashfile(HERE/"rows.json.gz")})
if __name__=="__main__":main()
