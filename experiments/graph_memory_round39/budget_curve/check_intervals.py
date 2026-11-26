"""Rebuild the three registered AUC contrasts by drawing trajectory IDs directly."""
from common import D,SEEDS,read,save
import numpy as np


def main():
    summary=read(D/"results.json")
    controls=["R35/firstfit","full_rgcn/firstfit","wo_chunk_adjacency/firstfit"]
    seed_rows=[read(D/f"test-{s}-outcomes.json.gz") for s in SEEDS]
    trajectories=sorted({r[0] for r in seed_rows[0].values()})
    location={t:i for i,t in enumerate(trajectories)}
    n=len(trajectories)
    sums=np.zeros((n,len(SEEDS),len(controls),2))
    counts=np.zeros(n,dtype=int)
    for s,rows in enumerate(seed_rows):
        for q,(t,scores) in rows.items():
            at=location[t]
            if s==0:
                counts[at]+=1
            for j,other in enumerate(controls):
                sums[at,s,j]+=np.subtract(scores["R35/graph_dp"][0],scores[other][0])
    random=np.random.default_rng(390039)
    fixed,crossed=[],[]
    for _ in range(100):
        samples=random.integers(n,size=(100,n))
        seed_samples=random.integers(len(SEEDS),size=(100,len(SEEDS)))
        for sample,ss in zip(samples,seed_samples):
            denominator=counts[sample].sum()
            d=sums[sample].sum(axis=0)/denominator
            fixed.append(d.mean(axis=0))
            crossed.append(d[ss].mean(axis=0))
    checked=0
    for mode,v in (("fixed_ci",fixed),("crossed_ci",crossed)):
        q=np.percentile(v,[2.5,97.5],axis=0)
        for i,other in enumerate(controls):
            reported=np.asarray(summary["contrasts"][other][mode])[:,:2]
            assert np.max(np.abs(q[:,i]-reported))<1e-12
            checked+=4
    save(D/"interval-check.json",dict(checked_interval_limits=checked,contrasts=controls,draws=10000,
        scheme="direct paired sampling of trajectories, then paired seed indices",max_allowed_difference=1e-12))
    print("Verified",checked,"AUC interval limits")


if __name__=="__main__":
    main()
