"""Recompute both arms, their seed SDs and all eight clustered paired intervals."""
from collections import defaultdict
from pathlib import Path
import json
import numpy as np
from collect import HERE,sha,get

def main():
    rows=get(HERE/"per-query.json.gz");src=get(HERE/"source.json");report=get(HERE/"results.json")
    assert sha(HERE/"per-query.json.gz")==src["rows_sha"] and sha(HERE/"results.json")==src["results"]
    assert src["results"]==src["hashes"]["five-seed-results.json"] and len(rows["rows"])==10000
    index=defaultdict(dict);group={}
    for seed,q,t,d,f in rows["rows"]:
        assert q not in index[seed]
        index[seed][q]=(d,f);assert group.setdefault(q,t)==t
    seeds=sorted(index);ids=sorted(group);metrics=rows["metrics"]
    assert set(map(int,src["test_weight_selections"]))==set(seeds)
    for rec in src["test_weight_selections"].values():
        assert rec["epoch_500"]==rec["epoch_580"]==1 and rec["weight_500"]==rec["weight_580"]
    assert seeds==report["seeds"] and all(set(index[s])==set(ids) for s in seeds)
    assert (len(ids),len(set(group.values())),len(metrics))==(2000,1207,8)
    x=np.asarray([[index[s][q] for q in ids] for s in seeds])
    means=x.mean(1)
    for j,k in enumerate(metrics):
        for i,arm in enumerate(("dense","factor")):
            ref=report["summary"][arm][k];arr=means[:,i,j]
            assert np.allclose((arr.mean(),arr.std(ddof=1)),(ref["mean"],ref["sd"]),rtol=0,atol=1e-11)
    changes=(x[:,:,1,:]-x[:,:,0,:]).mean(axis=0);names=sorted(set(group.values()))
    by={t:i for i,t in enumerate(names)}
    total=np.zeros((len(names),8));n=np.zeros(len(names),int)
    for q,delta in zip(ids,changes):
        i=by[group[q]];total[i]+=delta;n[i]+=1
    rng=np.random.default_rng(13);boot=[]
    for _ in range(100):
        ix=rng.integers(0,len(names),(100,len(names)))
        boot.extend(total[ix,:].sum(axis=1)/n[ix].sum(axis=1)[:,None])
    interval=np.quantile(boot,[.025,.975],axis=0)
    for j,k in enumerate(metrics):
        assert np.allclose((changes[:,j].mean(),*interval[:,j]),report["paired"][k],rtol=0,atol=1e-11)
    if (HERE/"manifest.json").exists():
        m=get(HERE/"manifest.json")
        assert all(sha(HERE/k)==h for k,h in m.items())
        assert set(m)=={f.name for f in HERE.iterdir() if f.is_file() and f.name!="manifest.json"}
    print("Verified 10000 paired rows, 8 metrics, 1207 clusters, five epochs selections and 8 bootstrap intervals.")
    for s,a in zip(seeds,means):print(s,round(a[0,3]*100,2),round(a[1,3]*100,2))
if __name__=="__main__":main()
