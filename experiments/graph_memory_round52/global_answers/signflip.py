"""Sensitivity analysis: two-sided sign flips of cluster-summed paired Answer F1."""
from pathlib import Path
import gzip,json
import numpy as np

def subsets(v):
    s=np.array([0.0])
    for d in v:s=np.concatenate((s-d,s+d))
    return s

def calculate(folder,left,right):
    read=lambda name:json.loads(gzip.decompress((folder/name).read_bytes()))
    records=read("records.json.gz");contexts=read("contexts.json.gz");sums={}
    for q,v in records.items():
        k=contexts[q]["first"];sums[k]=sums.get(k,0.)+v[left][0]-v[right][0]
    x=np.array([z for z in sums.values() if abs(z)>1e-12])
    observed=abs(x.sum());eps=1e-10
    if observed<eps:return dict(p=1.,nonzero_clusters=len(x),kind="exact",draws=2**len(x))
    if len(x)<=40:
        a=subsets(x[:len(x)//2]);b=np.sort(subsets(x[len(x)//2:]))
        # The two non-overlapping tails are evaluated for every first-half sum.
        extreme=int(np.searchsorted(b,-observed-a+eps,side="right").sum()+
                (len(b)-np.searchsorted(b,observed-a-eps,side="left")).sum())
        draws=2**len(x)
        return dict(p=extreme/draws,extreme=extreme,draws=draws,nonzero_clusters=len(x),kind="exact")
    rng=np.random.default_rng(523899);count=0;draws=1000000
    for _ in range(draws//1000):
        signs=rng.integers(0,2,size=(1000,len(x)),dtype=np.int8)*2-1
        count+=int((np.abs((signs*x).sum(axis=1))>=observed-eps).sum())
    return dict(p=(count+1)/(draws+1),extreme=count,draws=draws,nonzero_clusters=len(x),kind="monte_carlo",seed=523899)
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--confirm",action="store_true");args=p.parse_args()
    base=Path(__file__).resolve().parent
    folder=base/"confirm" if args.confirm else base
    left,right=("learned_dev","coord_cautious") if args.confirm else ("primary_href","primary_text")
    out=calculate(folder,left,right);out.update(metric="official Answer F1",contrast=[left,right],sidedness="two-sided",cluster="first document",role="secondary sensitivity")
    (folder/"signflip.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print(out)
