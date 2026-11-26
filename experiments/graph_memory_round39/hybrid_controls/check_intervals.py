"""Check AUC and FS@2048 with direct paired resampling of trajectory IDs."""
from shared import D,ORDERS,SEEDS,read,save
import numpy as np


def main():
    result=read(D/"results.json")
    inputs=[read(D/f"test-{s}-outcomes.json.gz") for s in SEEDS]
    trajectory=sorted({v[0] for v in inputs[0].values()})
    ix={t:i for i,t in enumerate(trajectory)}
    pairs=[]
    for o in ORDERS:
        for r in ("graph_density","firstfit","strict","graph_value"):
            pairs.append((o+"/graph_dp",o+"/"+r))
        pairs.append((o+"/graph_dp_equal_spend",o+"/graph_density"))
    summed=np.zeros((len(ix),len(SEEDS),len(pairs),2))
    count=np.zeros(len(ix),dtype=int)
    for i,data in enumerate(inputs):
        for t,rows in data.values():
            j=ix[t]
            count[j]+=int(i==0)
            for k,(a,b) in enumerate(pairs):
                x,y=rows[a],rows[b]
                summed[j,i,k]=summed[j,i,k]+[x[0][0]-y[0][0],x[1][3][0]-y[1][3][0]]
    fixed,crossed=[],[]
    gen=np.random.default_rng(390039)
    for block in range(100):
        samples=gen.integers(len(ix),size=(100,len(ix)))
        seed_samples=gen.integers(len(SEEDS),size=(100,len(SEEDS)))
        for sample,ss in zip(samples,seed_samples):
            m=summed[sample].sum(axis=0)/count[sample].sum()
            fixed.append(m.mean(axis=0))
            crossed.append(m[ss].mean(axis=0))
    maximum=0.
    for name,collection in (("ci95_fixed",fixed),("ci95_crossed",crossed)):
        expected=np.quantile(collection,[.025,.975],axis=0)
        for i,(a,b) in enumerate(pairs):
            ref=np.asarray(result["contrasts"][a+" minus "+b][name])[:,:2]
            maximum=max(maximum,float(np.abs(expected[:,i]-ref).max()))
    assert maximum<1e-12
    save(D/"interval-check.json",dict(replicates=10000,limits_verified=8*len(pairs),maximum_absolute_difference=maximum))
    print("Verified",8*len(pairs),"interval limits")


if __name__=="__main__":
    main()
