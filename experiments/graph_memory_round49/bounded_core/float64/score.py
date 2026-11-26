"""Regroup repeated time measurements by trajectory, then independently resample checkpoints' training seeds."""
from collections import defaultdict
from statistics import median
from run import D,S,h,read,write,np

def compute():
    seal=read(D/"seal.json");inputs=read(D/"inputs.json")
    mats=[];numbers={};removed=0;tail=0
    for seed in (13,17,29,37,41):
        p=D/f"runs-{seed}.json.gz"
        assert h(p)==seal["files"][p.name]
        qfile=S/f"input-{seed}.json.gz"
        assert h(qfile)==inputs[str(seed)]["source"]
        assert h(D/f"weights-{seed}.f64.gz")==inputs[str(seed)]["binary"]
        timing,ops=read(p);qrs=read(qfile)
        idx={tr:j for j,tr in enumerate(sorted({o["t"] for o in qrs.values()}))}
        arr=np.zeros((len(idx),2));blocks=defaultdict(list)
        for q,rep,m,ns in timing:blocks[q,m].append((rep,ns))
        for q,case in qrs.items():
            for m in range(2):
                ts=sorted(blocks[q,m]); assert [r for r,t in ts]==[1,2,3,4,5]
                arr[idx[case["t"]],m]+=median([t for r,t in ts])
        counts=np.asarray(list(ops.values())).reshape(-1,3)
        assert len(counts)==8000 and (counts[:,0]>=counts[:,1]).all()
        totals=counts.sum(axis=0);removed+=int(totals[1]);tail+=int(totals[0])
        numbers[str(seed)]=dict(ms=(arr.sum(axis=0)/1e6).tolist(),removed=int(totals[1]),tail=int(totals[0]),max_guard=int(counts[:,2].max()))
        mats.append(arr)
    rng=np.random.default_rng(49854);a=np.asarray(mats);n=a.shape[1]
    w=rng.multinomial(n,np.full(n,1/n),size=6000).astype(float)
    sw=rng.multinomial(5,np.full(5,.2),size=6000).astype(float)
    boot=np.stack([w@v for v in a],axis=1)
    output={}
    for key,b,c in (("seed13",boot[:,0,:],a[0]),("all",np.einsum("rs,rsm->rm",sw,boot),a.mean(axis=0))):
        t=c.sum(axis=0)/1e6;rr=b[:,0]/b[:,1]
        output[key]=dict(full_ms=t[0],guarded_ms=t[1],speedup=t[0]/t[1],ci=np.percentile(rr,[2.5,97.5]).tolist())
    return dict(timing=output,per_seed=numbers,removed=removed,total=tail,ordered_matches=sum(seal["checked"].values()))
if __name__=="__main__":
    results=compute();write(D/"results.json",results);print(results["timing"],results["removed"],results["total"])
