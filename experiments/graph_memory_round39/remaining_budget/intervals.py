"""Paired bootstrap at the trajectory level, with a second crossed-seed interval."""
import os
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[k]="1"
import numpy as np
SEEDS=(13,17,29,37,41)
METRICS=("FullSupport2048","Coverage2048","tokens","units")

def summarize(mats,trajectory,contrasts):
    ts,ix=np.unique(trajectory,return_inverse=True);assert len(ts)==1207 and len(ix)==2000
    groups=np.bincount(ix)
    means={k:v.mean(axis=(0,1)).tolist() for k,v in mats.items()}
    by_seed={str(s):{k:v[i].mean(axis=0).tolist() for k,v in mats.items()} for i,s in enumerate(SEEDS)}
    arr=np.stack([mats[a]-mats[b] for a,b in contrasts],axis=2).transpose(1,0,2,3)
    nseed,ncmp,nmet=arr.shape[1:]
    cl=np.zeros((len(ts),nseed,ncmp,nmet));np.add.at(cl,ix,arr)
    cf=[];cc=[];rng=np.random.default_rng(390039)
    for _ in range(100):
        sample=rng.integers(len(ts),size=(100,len(ts)))
        reps=np.stack([np.bincount(r,minlength=len(ts)) for r in sample])
        v=(reps@cl.reshape(len(ts),-1)).reshape(100,nseed,ncmp,nmet)/(reps@groups)[:,None,None,None]
        cf.append(v.mean(axis=1));si=rng.integers(nseed,size=(100,nseed));cc.append(v[np.arange(100)[:,None],si].mean(axis=1))
    fixed=np.quantile(np.concatenate(cf),[.025,.975],axis=0);cross=np.quantile(np.concatenate(cc),[.025,.975],axis=0)
    deltas=arr.mean(axis=(0,1));output={}
    for i,(a,b) in enumerate(contrasts):
        output[a+" minus "+b]=dict(delta=deltas[i].tolist(),ci95_fixed=fixed[:,i].tolist(),ci95_crossed=cross[:,i].tolist(),
             wins=(arr[:,:,i,0]>0).sum(axis=0).tolist(),losses=(arr[:,:,i,0]<0).sum(axis=0).tolist())
    return dict(rows=2000,trajectories=1207,seeds=SEEDS,metrics=METRICS,means=means,per_seed=by_seed,contrasts=output,bootstrap=10000)

