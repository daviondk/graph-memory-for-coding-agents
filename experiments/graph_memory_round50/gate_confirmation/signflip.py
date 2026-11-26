"""Conditional two-sided sign randomization for the primary paired F1 differences."""
import argparse,itertools,math
import numpy as np
from paths_a import *

def run(split):
    check()
    if split=="old":
        path=A/"outcomes.json.gz";assert sha(path)==get(A/"manifest.json")["files"]["outcomes.json.gz"]
    else:
        path=D/"outcomes.json.gz";assert sha(path)==get(D/"results.json")["outcomes"]
    outcomes=get(path);diffs={q:v["arms"]["adaptive"][1]-v["arms"]["dense"][1] for q,v in sorted(outcomes.items())}
    nonzero={q:d for q,d in diffs.items() if d!=0};w=np.asarray(list(map(abs,nonzero.values())),dtype=np.float64)
    observed=abs(math.fsum(nonzero.values()));k=len(w)
    if k<=20:
        draws=1<<k;extreme=0
        for start in range(0,draws,2048):
            n=np.arange(start,min(draws,start+2048),dtype=np.int64)
            signs=2*((n[:,None]>>np.arange(k)[None,:])&1)-1
            extreme+=int(np.sum(np.abs(signs@w)>=observed-1e-12))
        p=extreme/draws;method="exact"
    else:
        draws=1_000_000;rng=np.random.default_rng(500731);extreme=0
        for start in range(0,draws,2000):
            signs=rng.integers(0,2,size=(min(draws-start,2000),k),dtype=np.int8)*2-1
            extreme+=int(np.sum(np.abs(signs@w)>=observed-1e-12))
        p=(extreme+1)/(draws+1);method="monte-carlo-plus-one"
    result=dict(n=len(diffs),k=k,wins=sum(v>0 for v in nonzero.values()),losses=sum(v<0 for v in nonzero.values()),
                pp=100*math.fsum(diffs.values())/len(diffs),two_sided_p=p,extreme=extreme,draws=draws,
                method=method,seed=500731,observed_abs_sum=observed,nonzero=nonzero,outcomes=sha(path))
    put(D/("signflip-"+split+".json"),result)
    print(split,result["n"],k,extreme,draws,p,flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("split",choices=["old","new"]);run(parser.parse_args().split)
