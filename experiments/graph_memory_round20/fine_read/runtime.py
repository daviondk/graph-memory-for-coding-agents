"""CPU post-ranking cost on a deterministic sample. No evidence labels are loaded."""
import os
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[k]="1"
import gc
import gzip,hashlib,json,platform,time
from collections import defaultdict
import numpy as np
import reader as rd
def pack(rr,blocks,g,x,rp,m):
    parent,_,owners,_,_,_=g
    z=x[:,m["columns"]];s=1/(1+np.exp(-np.clip((z-m["mean"])/m["scale"]@m["coef"]+m["offset"],-200,200)))
    costs=np.array([b[3] for b in blocks]);order=np.lexsort((np.arange(len(s)),-s/costs))
    keep=[n["node_id"] for n in rr[:2]];used=defaultdict(list);left=2048
    for k in keep:
        e,a,b,c=parent[k];used[e].append((a,b));left-=c
    for j in order:
        e,a,b,c,_=blocks[j]
        if owners[j] and c<=left and all(b<=l or h<=a for l,h in used[e]):
            keep.append("micro/"+str(j));left-=c
            if left==0:break
    return keep
def main():
    sf=rd.OLD/"trained_rank";ranks={};loc={};reference={}
    for i in range(8):
        for r in rd.load(rd.source("dense",i)):ranks.setdefault(r["t"],[]).append(r)
        for r in rd.load(rd.D/f"dense-decisions-{i}.json.gz"):loc[r["t"]]=i;reference[r["t"]]=r["picks"]
    ids=set(sorted(ranks,key=lambda t:hashlib.sha256(("r20-cost/v1/"+t).encode()).digest())[:128]);rows=[];model=rd.load(rd.D/"model.json")
    for i in range(8):
        with gzip.open(rd.blocks_path("dense",i),"rb") as f:
            for line in f:
                base=json.loads(line);t=base["t"]
                if t not in ids:continue
                r=min(ranks[t],key=lambda v:hashlib.sha256(v["q"].encode()).digest())
                q,rr=r["q"],r["rr"];raw=rd.load(rd.stream.CACHE/f"{i}-{t}.json.gz")
                query=dict(raw["q"])[q];bl=base["blocks"];start=time.perf_counter_ns();g=rd.geometry(base,raw,rr)
                prep=time.perf_counter_ns()-start
                def whole():
                    left=2048;keep=[]
                    for p in rr:
                        if p["token_count"]<=left:
                            keep.append(p["node_id"]);left-=p["token_count"]
                    return keep
                def fine():
                    x,rp,_=rd.features(query,rr,bl,g);return pack(rr,bl,g,x,rp,model["models"]["full"])
                elapsed={"skip":[],"ratio":[]}
                for rep in range(6):
                    for k,fn in ((("skip",whole),("ratio",fine)) if (len(rows)+rep)%2 else (("ratio",fine),("skip",whole))):
                        start=time.perf_counter_ns();sel=fn();dt=time.perf_counter_ns()-start
                        assert sel==reference[t][q][k]
                        if rep:elapsed[k].append(dt)
                rows.append({"q":q,"t":t,"parents":len(rr),"blocks":len(bl),"precompute_ns":prep,"query_ns":elapsed})
    assert len(rows)==128;rd.save(rd.D/"runtime-sample.json.gz",rows)
    dist={}
    for name,times in (("full_index_build",[r["precompute_ns"] for r in rows]),("skip",[np.median(r["query_ns"]["skip"]) for r in rows]),("ratio",[np.median(r["query_ns"]["ratio"]) for r in rows])):
        dist[name]=dict(zip(("p25_ms","median_ms","p75_ms","p95_ms"),np.quantile(np.array(times)/1e6,[.25,.5,.75,.95]).tolist()))
    rd.save(rd.D/"runtime-summary.json",{"n":128,"host":platform.processor(),"quantiles":dist,"cached_E5_ranks":True,"repetitions":5,"code":rd.sha(rd.D/"runtime.py")})
if __name__=="__main__":main()
