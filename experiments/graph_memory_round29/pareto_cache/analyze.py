"""Article-clustered paired cost and latency contrasts at fixed cache cardinality."""
from collections import defaultdict
import numpy as np
from cache_study import D,PRE,ARMS,init,read,save,sha
def main():
    p,old,logs,memory,dest=init();c=read(D/"costs.json.gz");m=read(D/"measurement-seal.json");built=read(D/"build-seal.json")
    scen=read(PRE/"scenarios.json.gz");times=read(D/"latency.json.gz");t=defaultdict(list)
    for q,co,arm,rep,ns in times:t[q,co,arm].append(ns/1e3)
    counts={};timing={};contrasts={};labels=sorted(set(scen[q]["article"] for q in c));all_cases=sorted(next(iter(c.values())))
    subsets=("all","independent","targeted",*all_cases)
    for subset in subsets:
        def keep(co):return subset=="all" or co==subset or co.split("-")[0]==subset
        ids=sorted((q,co) for q,cs in c.items() for co in cs if keep(co))
        ti=sorted((q,co) for q,co,arm in t if arm==ARMS[0] and keep(co));counts[subset]={};timing[subset]={};contrasts[subset]={}
        groups=[np.array([i for i,(q,co) in enumerate(ids) if scen[q]["article"]==a]) for a in labels]
        tl=sorted({scen[q]["article"] for q,co in ti})
        tgroups=[np.array([i for i,(q,co) in enumerate(ti) if scen[q]["article"]==a]) for a in tl]
        rng=np.random.default_rng(29997);draws=rng.integers(len(groups),size=(10000,len(groups)))
        tdraws=rng.integers(len(tgroups),size=(10000,len(tgroups)))
        val=np.array([[c[q][co][a] for a in ARMS] for q,co in ids]);ms=np.array([[np.median(t[q,co,a]) for a in ARMS] for q,co in ti])
        for j,a in enumerate(ARMS):
            counts[subset][a]={"n":len(ids),**dict(zip(m["cost_fields"],[int(v) for v in val[:,j,:].sum(axis=0)]))}
            timing[subset][a]={"timed_qevents":len(ti),"p50":float(np.median(ms[:,j])),"p95":float(np.quantile(ms[:,j],.95))}
        for k,r,pp in ((8,0,1),(64,2,3)):
            change=val[:,r,0]-val[:,pp,0]
            assert np.all(change>=0)
            group_change=np.array([change[ix].mean() for ix in groups]);gain=group_change[draws].mean(axis=1)
            ratios=[np.median(ms[ix,pp])/np.median(ms[ix,r]) for ix in [np.concatenate([tgroups[j] for j in draw]) for draw in tdraws]]
            contrasts[subset][str(k)]={"rescued":int(change.sum()),"regressed":int((change<0).sum()),
                "hit_gain_pp":float(100*change.mean()),"hit_gain_ci_pp":(100*np.percentile(gain,[2.5,97.5])).tolist(),
                "latency_p50_ratio":float(np.median(ms[:,pp])/np.median(ms[:,r])),"latency_p50_ratio_ci":np.percentile(ratios,[2.5,97.5]).tolist()}
    shared=(logs/"bounds.sqlite").stat().st_size+(logs/"zip.sqlite").stat().st_size
    results={"strict":m["strict"],"timing_samples":len(times),"base_bytes":shared,"cache_stores":built["stores"],
            "online_bytes":{k:v["bytes"]+shared for k,v in built["stores"].items()},"costs":counts,"timing":timing,"contrasts":contrasts}
    save(D/"results.json",results)
    for s in ("all","independent","targeted","targeted-8"):
        print(s,counts[s],timing[s],contrasts[s])
    print("storage",results["online_bytes"])
if __name__=="__main__":main()
