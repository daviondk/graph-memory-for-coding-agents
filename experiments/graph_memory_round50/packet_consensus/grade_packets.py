"""Validate budgets, source-span coverage and paired trajectory intervals."""
import hashlib
import numpy as np
from run import BASE, D, SEEDS, read, put, sha
from pathlib import Path

STREAM=D.parents[1]/"graph_memory_round49/stream_packet"

def signed(dir,name):
    assert sha(dir/name)==read(dir/"manifest.json")["files"][name]
    return read(dir/name)

def grade():
    assert sha(D/"packets.json.gz")==read(D/"forecast-seal.json")["forecasts"]
    rows=read(D/"packets.json.gz")
    gold=signed(STREAM,"judgments.json.gz")
    src=signed(BASE,"pool.json.gz")
    own=signed(BASE,"scores.json.gz")
    outcomes={}
    for q,(t,panels) in rows.items():
        spans=gold[hashlib.sha256(q.encode()).hexdigest()]
        total=sum(w for w,ids in spans)
        result=[]
        for cp,packets in enumerate(panels):
            metrics={}
            for arm,ids in packets.items():
                sel=set(ids)
                assert len(ids)==len(sel)
                tokens=sum(src[q]["c"][i] for i in ids)
                assert tokens<=2048
                covered=sum(w for w,witnesses in spans if sel.intersection(witnesses))
                metrics[arm]=[int(covered==total),covered/total,tokens]
            for j,s in enumerate(SEEDS):
                old=own[q][1][j][cp][0]
                assert np.allclose(metrics[f"single_{s}"],old,atol=1e-12,rtol=0)
            metrics["mean_single"]=np.mean([metrics[f"single_{s}"] for s in SEEDS],axis=0).tolist()
            result.append(metrics)
        outcomes[q]=[t,result]
    return outcomes

def analysis(outcomes):
    groups=sorted({t for t,_ in outcomes.values()})
    group_id={t:i for i,t in enumerate(groups)}
    arms=sorted(a for a in next(iter(outcomes.values()))[1][0] if not a.startswith("single_"))
    result={}
    for cp in (0,1):
        values=np.zeros((len(groups),len(arms),3))
        counts=np.zeros(len(groups))
        for t,panels in outcomes.values():
            i=group_id[t]
            counts[i]+=1
            values[i]+=[panels[cp][a] for a in arms]
        means=values.sum(axis=0)/counts.sum()
        rng=np.random.default_rng(50084)
        blocks=[]
        for _ in range(100):
            samples=rng.multinomial(len(groups),np.full(len(groups),1/len(groups)),size=100)
            blocks.append(samples @ values[:,:,0]/(samples @ counts)[:,None])
        boot=np.concatenate(blocks)
        comparisons={}
        for target in arms:
            ti=arms.index(target)
            comparisons[target]={}
            for j,name in enumerate(arms):
                delta=100*(boot[:,ti]-boot[:,j])
                comparisons[target][name]=[float(100*(means[ti,0]-means[j,0])),*np.percentile(delta,[2.5,97.5]).tolist()]
        result[("recall","full_support")[cp]]=dict(means={a:means[j].tolist() for j,a in enumerate(arms)},contrasts=comparisons)
    return result
if __name__=="__main__":
    obs=grade()
    put(D/"outcomes.json.gz",obs)
    res=analysis(obs)
    put(D/"results.json",res)
    for cfg,r in res.items():print(cfg,r["means"],r["contrasts"]["votes_dp"]["mean_dp"])

