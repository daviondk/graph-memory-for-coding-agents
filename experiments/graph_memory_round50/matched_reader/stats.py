"""Paired crossed cluster/seed bootstrap. All methods share the very same resampled units."""
import os
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
import numpy as np
from common import D,SEEDS,MODES,CONFIG,put,read

def calculate(scores,times):
    qs=sorted(scores);ts,ix=np.unique([scores[q][0] for q in qs],return_inverse=True)
    # Shape q, seed, checkpoint, method, [FS, coverage, token count, select us, full us].
    a=np.array([scores[q][1] for q in qs],float)
    t=np.stack([np.median(np.asarray([times[s][q] for q in qs],dtype=float),axis=-1) for s in SEEDS],axis=1)/1000
    d=np.concatenate((a,t),axis=-1);mx=d.mean(axis=(0,1))
    pairs=[(1,0),(1,2),(1,3),(1,4),(4,3)]
    result={"n":len(qs),"clusters":len(ts),"bootstrap":6000,"bootstrap_seed":501994,"seeds":list(SEEDS),"checkpoints":{}}
    sums=np.zeros((len(ts),*d.shape[1:]));np.add.at(sums,ix,d)
    count=np.bincount(ix)
    boot=[];rng=np.random.default_rng(501994)
    for _ in range(60):
        draw=rng.integers(len(ts),size=(100,len(ts)))
        weights=np.stack([np.bincount(x,minlength=len(ts)) for x in draw])
        out=(weights@sums.reshape(len(ts),-1)).reshape((100,*d.shape[1:]))/(weights@count)[:,None,None,None,None]
        si=rng.integers(5,size=(100,5))
        boot.append(out[np.arange(100)[:,None],si].mean(axis=1))
    samp=np.concatenate(boot,axis=0)
    def ci(v):return np.quantile(v,[.025,.975],axis=0).T.tolist()
    for k,cp in enumerate(CONFIG):
        arms={}
        for m,name in enumerate(MODES):
            arms[name]={"mean":mx[k,m,:].tolist(),"select_qus":np.quantile(t[:,:,k,m,0],[.5,.95]).tolist(),"pool_qus":np.quantile(t[:,:,k,m,1],[.5,.95]).tolist()}
        comparisons=[]
        for l,r in pairs:
            delta=mx[k,l,:3]-mx[k,r,:3]
            sr=mx[k,r,3:]/mx[k,l,3:]
            diff=a[:,:,k,l,0]-a[:,:,k,r,0]
            comparisons.append({"left":MODES[l],"right":MODES[r],"quality_delta":delta.tolist(),"quality_ci":ci(samp[:,k,l,:3]-samp[:,k,r,:3]),"right_time_over_left":sr.tolist(),"time_ratio_ci":ci(samp[:,k,r,3:]/samp[:,k,l,3:]),"wins":int((diff>0).sum()),"losses":int((diff<0).sum())})
        result["checkpoints"][cp]={"arms":arms,"comparisons":comparisons}
    return result

if __name__=="__main__":
    result=calculate(read(D/"scores.json.gz"),{s:read(D/f"times-{s}.json.gz") for s in SEEDS})
    put(D/"results.json",result)
    for c,rec in result["checkpoints"].items():
        print(c,[(v["right"],v["right_time_over_left"],v["quality_delta"][0]) for v in rec["comparisons"]],flush=True)

