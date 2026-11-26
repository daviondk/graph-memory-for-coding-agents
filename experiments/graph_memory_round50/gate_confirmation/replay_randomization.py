"""Repeat both recorded exact/Monte Carlo null distributions from local score differences only."""
import itertools,json,math
from pathlib import Path

def main():
    root=Path(__file__).resolve().parent
    for split in ("old","new"):
        v=json.loads((root/f"signflip-{split}.json").read_bytes())
        ds=[d for _,d in sorted(v["nonzero"].items())]
        tol=abs(math.fsum(ds))-1e-12
        if v["method"]=="exact":
            signed=[0.]
            for d in ds:signed=[x+abs(d) for x in signed]+[x-abs(d) for x in signed]
            count=sum(abs(s)>=tol for s in signed)
        else:
            import numpy as np
            rng=np.random.default_rng(v["seed"])
            weights=np.abs(ds);count=0
            for start in range(0,v["draws"],2000):
                n=min(2000,v["draws"]-start)
                bits=rng.integers(0,2,size=(n,len(ds)),dtype=np.int8)
                totals=np.sum(weights*(2*bits-1),axis=1)
                count+=int(np.count_nonzero(np.abs(totals)>=tol))
        assert count==v["extreme"],(split,count,v["extreme"])
        print(split,v["method"],count,v["draws"],v["two_sided_p"])
if __name__=="__main__":main()
