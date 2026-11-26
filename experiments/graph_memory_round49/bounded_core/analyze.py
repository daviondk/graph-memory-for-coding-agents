"""Estimate paired costs and upper-bound reductions over complete trajectories and training seeds."""
from collections import defaultdict
from statistics import median
from pathlib import Path
import numpy as np
from bench_core import D,S,read,write,h

def calculate():
    seal=read(D/"forecast-seal.json")
    for name,digest in seal["payload"].items():assert h(D/name)==digest
    seeds=(13,17,29,37,41);times=[];work=[];diagnostic={}
    for seed in seeds:
        assert h(S/f"input-{seed}.json.gz")==seal["input"][str(seed)]
        data=read(S/f"input-{seed}.json.gz")
        src=read(S/f"ledger-{seed}.json.gz")
        odd=seal["different"][str(seed)]
        assert sorted(odd)==sorted(src["different_q32_packets"])
        idx={tr:k for k,tr in enumerate(sorted({r["t"] for r in data.values()}))}
        obs=defaultdict(list)
        for q,rep,mode,ns in read(D/f"timing-{seed}.json.gz"):obs[q,mode].append((rep,ns))
        costs=np.zeros((len(idx),4));sum_work=np.zeros((4,8),dtype=np.int64)
        impacted=np.zeros(4,dtype=np.int64)
        raw=read(D/f"work-{seed}.json.gz")
        for q,case in data.items():
            tr=idx[case["t"]]
            for mode in range(4):
                ranked=sorted(obs[q,mode])
                assert [r for r,t in ranked]==[1,2,3,4,5]
                costs[tr,mode]+=median([t for r,t in ranked])
                traces=np.asarray(raw[q][str(mode)],dtype=np.int64).reshape(4,8)
                assert np.all(traces[:,:5]>=0)
                if mode:
                    active=traces[:,7]==0
                    assert np.all(traces[active,0]==traces[active,1:4].sum(axis=1))
                sum_work[mode]+=traces.sum(axis=0)
                impacted[mode]+=int(any(traces[:,5]))
        times.append(costs);work.append(sum_work)
        diagnostic[str(seed)]=dict(work=sum_work.tolist(),improved_queries=impacted.tolist(),original_differences=len(odd))
    a=np.asarray(times);n=a.shape[1]
    gen=np.random.default_rng(49843); samples=6000
    # Primary trajectory bootstrap and secondary crossed resampling of trajectories and training seeds.
    trajectory=gen.multinomial(n,np.full(n,1/n),size=samples).astype(float)
    seedweight=gen.multinomial(5,np.full(5,.2),size=samples).astype(float)
    boot=np.stack([trajectory@x for x in a],axis=1)
    report={}
    for key,inds in [('seed13',[0]),('all',list(range(5)))]:
        v=a[inds].sum(axis=(0,1))/len(inds)/1e6
        b=boot[:,0,:] if key=='seed13' else np.einsum('rs,rsm->rm',seedweight,boot)
        contrasts={}
        for baseline,method in [(0,1),(0,2),(1,2),(3,2)]:
            z=b[:,baseline]/b[:,method]
            contrasts[f"{baseline}/{method}"]=dict(speedup=v[baseline]/v[method],ci=np.percentile(z,[2.5,97.5]).tolist())
        report[key]=dict(ms=v.tolist(),ratios=contrasts,work=np.sum(np.asarray(work)[inds],axis=0).tolist())
    return dict(summary=report,seeds=diagnostic,replicates=samples,ordered_matches=40000,
                original_matches=40000-sum(len(x) for x in seal["different"].values()),exhaustive=seal["exhaustive"])
if __name__=="__main__":
    out=calculate();write(D/"results.json",out);print(out["summary"])
