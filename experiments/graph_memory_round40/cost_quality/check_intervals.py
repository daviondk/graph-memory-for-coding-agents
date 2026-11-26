"""Independent direct bootstrap for the demo decision's quality and latency contrasts."""
from inputs import D,PREV,SEEDS,MODES,REF,read,save
from runtime import np


def main():
    r=read(D/"results.json")
    trajectories=sorted({v[0] for v in read(D/"warm-13.json.gz").values()})
    ix={t:i for i,t in enumerate(trajectories)}
    pairs=[("raw","dp"),("density","dp"),("native","dp"),("raw","native")]
    totals=np.zeros((len(ix),len(SEEDS),len(pairs),2))
    counts=np.zeros(len(ix))
    for s,seed in enumerate(SEEDS):
        times=read(D/f"warm-{seed}.json.gz")
        gold=read(PREV/f"test-{seed}-outcomes.json.gz")
        for q,(t,hashes,timings) in times.items():
            i=ix[t]
            counts[i]+=int(s==0)
            scores=[gold[q][1]["wo_chunk_adjacency/"+rule][1][3][0] for rule in REF]
            med=[sorted(rec[-1] for rec in rows)[1]/1000 for rows in timings]
            for k,(a,b) in enumerate(pairs):
                j1,j2=MODES.index(a),MODES.index(b)
                totals[i,s,k]+=[scores[j1]-scores[j2],med[j1]-med[j2]]
    rng=np.random.default_rng(400240)
    fixed,crossed=[],[]
    for _ in range(100):
        samples=rng.integers(len(ix),size=(100,len(ix)))
        seed_samples=rng.integers(5,size=(100,5))
        for sample,ss in zip(samples,seed_samples):
            value=totals[sample].sum(axis=0)/counts[sample].sum()
            fixed.append(value.mean(axis=0))
            crossed.append(value[ss].mean(axis=0))
    error=0
    for label,values in (("fixed",fixed),("crossed",crossed)):
        bounds=np.quantile(values,[.025,.975],axis=0)
        for k,(a,b) in enumerate(pairs):
            recorded=np.asarray(r["contrasts"][a+" minus "+b][label])[:,[0,-1]]
            error=max(error,float(np.abs(bounds[:,k]-recorded).max()))
    assert error<1e-9
    save(D/"interval-check.json",dict(limits=8*len(pairs),max_absolute_error=error,draws=10000))
    print("Checked",8*len(pairs),"bounds")


if __name__=="__main__":
    main()
