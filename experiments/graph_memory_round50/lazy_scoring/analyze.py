from benchmark import D, MODES, SEEDS, read, put, sha
import numpy as np

def summaries():
    traces={}
    times=[]
    for seed in SEEDS:
        name=f"times-{seed}.json.gz"
        assert sha(D/name)==read(D/"run-seal.json")["files"][name]
        measured={}
        for q,cp,t,counts,reps in read(D/name):
            assert t==traces.setdefault(q,t) and [len(r) for r in reps]==[3]*len(MODES)
            assert all(min(r)>0 for r in reps)
            measured[q,cp]=np.median(reps,axis=1)/1000,counts
        assert len(measured)==4000
        times.append(measured)
    groups=sorted(set(traces.values())); index={t:i for i,t in enumerate(groups)}
    assert len(groups)==1207 and len(traces)==2000
    result={}
    for cp in (0,1):
        ts=np.zeros((len(groups),len(SEEDS),4))
        flat=[];before=after=all_fit=0
        for q,t in traces.items():
            for j,run in enumerate(times):
                v,n=run[q,cp];ts[index[t],j]+=v;flat.append(v)
                before+=n[0];after+=n[1];all_fit+=n[1]==0
        flat=np.asarray(flat)
        rng=np.random.default_rng(50061)
        blocks=[]
        for _ in range(100):
            w=rng.multinomial(len(groups),np.full(len(groups),1/len(groups)),size=100)
            s=rng.multinomial(len(SEEDS),np.full(len(SEEDS),1/len(SEEDS)),size=100)
            z=(w @ ts.reshape(len(groups),-1)).reshape(100,len(SEEDS),4)
            blocks.append(np.einsum("bs,bsm->bm",s,z))
        boot=np.concatenate(blocks)
        comparisons={}
        for a,b in ((0,1),(2,3),(0,2),(0,3),(1,3)):
            ratio=boot[:,a]/boot[:,b]
            comparisons[MODES[a]+"/"+MODES[b]]=[float(flat[:,a].sum()/flat[:,b].sum()),*np.percentile(ratio,[2.5,97.5]).tolist()]
        result[("recall","full_support")[cp]]=dict(rows=before,scored=after,skipped_all=int(all_fit),
            mean_us=dict(zip(MODES,flat.mean(axis=0).tolist())),q50_us=dict(zip(MODES,np.median(flat,axis=0).tolist())),
            q95_us=dict(zip(MODES,np.percentile(flat,95,axis=0).tolist())),comparisons=comparisons)
    return result
if __name__=="__main__":
    r=summaries()
    put(D/"results.json",r)
    for cp,v in r.items(): print(cp,v["rows"],v["scored"],v["skipped_all"],v["mean_us"],v["comparisons"])

