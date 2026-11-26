from inputs import D,PREV,SEEDS,MODES,REF,read,save,sha
from runtime import np
import hashlib
import json

METRICS=("FS2048","Coverage2048","tokens","selector_cached_us","features_us","model_us","selector_online_us","online_us")


def main():
    times=read(D/"time-seal.json")
    data=np.zeros((len(SEEDS),2000,len(MODES),len(METRICS)))
    observations=[]
    questions=traces=None
    by_seed={}
    for s,seed in enumerate(SEEDS):
        tp=D/f"warm-{seed}.json.gz"
        assert times["stages"][str(seed)]["sha"]==sha(tp)
        t=read(tp)
        pp=PREV/f"test-{seed}-packets.json.gz";op=PREV/f"test-{seed}-outcomes.json.gz"
        pseal=read(PREV/f"test-{seed}-seal.json")
        assert sha(pp)==pseal["packets"] and sha(op)==read(PREV/f"test-{seed}-score-seal.json")["outcomes"]
        pred,qout=read(pp),read(op)
        assert t.keys()==pred.keys()==qout.keys()
        if questions is None:
            questions=sorted(t)
            traces=[t[q][0] for q in questions]
        assert questions==sorted(t)
        reps=np.zeros((2000,len(MODES),3,5))
        for i,q in enumerate(questions):
            tr,hashes,values=t[q]
            assert tr==traces[i]==qout[q][0]==pred[q][0]
            for j,ref in enumerate(REF):
                idx=pseal["rules"].index(ref)
                seq=pred[q][1][1][3][idx]
                assert hashes[j]==hashlib.sha256(json.dumps(seq,separators=(",",":")).encode()).hexdigest()
                data[s,i,j,:3]=qout[q][1]["wo_chunk_adjacency/"+ref][1][3][:3]
            reps[i]=values
        observations.append(reps)
        data[s,:,:,3:]=np.median(reps,axis=2)/1000
        by_seed[str(seed)]={m:data[s,:,j].mean(axis=0).tolist() for j,m in enumerate(MODES)}
    avg=data.mean(axis=(0,1))
    raw=np.stack(observations)
    desc={}
    for m,mode in enumerate(MODES):
        matrix=raw[:,:,m,:,:].reshape(-1,5)/1000
        desc[mode]={k:dict(p50=float(np.median(matrix[:,j])),p95=float(np.quantile(matrix[:,j],.95)),
                             mean=float(np.mean(matrix[:,j]))) for j,k in enumerate(METRICS[3:])}
    ts,ix=np.unique(traces,return_inverse=True)
    assert len(ts)==1207 and len(questions)==2000
    pairs=[(a,b) for a in MODES for b in MODES if a!=b]
    diffs=np.stack([data[:,:,MODES.index(a)]-data[:,:,MODES.index(b)] for a,b in pairs],axis=2)
    cl=np.zeros((len(ts),len(SEEDS),len(pairs),len(METRICS)))
    np.add.at(cl,ix,diffs.transpose(1,0,2,3))
    size=np.bincount(ix)
    fixed,crossed=[],[]
    gen=np.random.default_rng(400240)
    for _ in range(100):
        sample=gen.integers(len(ts),size=(100,len(ts)))
        freq=np.stack([np.bincount(x,minlength=len(ts)) for x in sample]).astype(float)
        vals=(freq@cl.reshape(len(ts),-1)).reshape(100,*cl.shape[1:])/(freq@size)[:,None,None,None]
        seed_ix=gen.integers(len(SEEDS),size=(100,len(SEEDS)))
        fixed.append(vals.mean(axis=1))
        crossed.append(vals[np.arange(100)[:,None],seed_ix].mean(axis=1))
    fi=np.quantile(np.concatenate(fixed),[.025,.975],axis=0)
    ci=np.quantile(np.concatenate(crossed),[.025,.975],axis=0)
    contrasts={}
    for i,(a,b) in enumerate(pairs):
        contrasts[a+" minus "+b]=dict(delta=diffs[:,:,i].mean(axis=(0,1)).tolist(),fixed=fi[:,i].tolist(),crossed=ci[:,i].tolist())
    eligible=[m for m in MODES if m=="dp" or contrasts[m+" minus dp"]["crossed"][0][0]>=-.005]
    choice=min(eligible,key=lambda m:avg[MODES.index(m),-1])
    cold=read(D/"cold.json")
    fields=("wall_ns","input_ns","import_ns","model_and_library_ns","first_call_ns")
    cold_desc={}
    for mode in MODES:
        rr=[v for v in cold["runs"] if v["mode"]==mode]
        cold_desc[mode]={f.removesuffix("_ns")+"_ms":float(np.median([v[f] for v in rr])/1e6) for f in fields}
    out=dict(seeds=SEEDS,n_questions=2000,n_trajectories=len(ts),timed_calls=240000,cold_measured_processes=20,
             source_ledger_hashes={str(s):sha(PREV/f"test-{s}-outcomes.json.gz") for s in SEEDS},
             metrics=METRICS,means={m:avg[j].tolist() for j,m in enumerate(MODES)},per_seed=by_seed,
             desc_raw_replicas=desc,cold_medians=cold_desc,bootstraps=10000,bootstrap_seed=400240,contrasts=contrasts,
             choice=choice,tolerance_pp=.5,eligible=eligible,time_seal=sha(D/"time-seal.json"))
    save(D/"results.json",out)
    print("selected",choice,"eligible",eligible)
    for j,m in enumerate(MODES):
        print(m,[round(v,4) for v in avg[j]],desc[m]["online_us"],cold_desc[m])
    for a,b in (("raw","dp"),("raw","native"),("raw","density")):
        p=contrasts[a+" minus "+b]
        print(a,b,[100*p["delta"][0],p["delta"][-1]],[[100*x[0],x[-1]] for x in p["crossed"]])


if __name__=="__main__":
    main()
