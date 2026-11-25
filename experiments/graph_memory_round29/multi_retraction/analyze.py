"""Summarize comparable workloads with uncertainty clustered by source article."""
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np
from multiban_design import D,MODES,read,save,sha
from store import state

def main():
    p,cases,old,logs,base=state();m=read(D/"measurement-seal.json")
    preds=read(D/"predictions.json.gz");sc=read(D/"scenarios.json.gz");build=read(D/"build-rows.json.gz")
    t=read(D/"latency.json.gz");timings=defaultdict(list)
    for q,cond,arm,rep,ns in t:timings[q,cond,arm].append(ns/1e3)
    selections=defaultdict(list);events=defaultdict(list)
    for q,rs in sc.items():
        for kind in ("targeted","independent"):
            for k,lst in rs[kind].items():
                cond=kind+"-"+k
                selections[cond].append(len(lst));events[cond].append(len(preds[q][cond]["ban"]))
    clocks={};costs={}
    conditions=sorted(selections)
    for sub in ["all",*conditions]:
        qs=sorted((q,c) for q,c,arm in timings if arm=="full" and (sub=="all" or c==sub))
        mat=np.array([[np.median(timings[q,c,arm]) for arm in MODES] for q,c in qs])
        titles=sorted({sc[q]["article"] for q,c in qs})
        index=[[i for i,(q,c) in enumerate(qs) if sc[q]["article"]==art] for art in titles]
        rng=np.random.default_rng(29699)
        def eff(x):
            med=np.median(x,axis=0)
            return [med[1]/med[0],med[2]/med[1],med[1]/med[3]]
        draws=[eff(mat[np.concatenate([index[j] for j in dd])]) for dd in rng.integers(len(titles),size=(10000,len(titles)))]
        clocks[sub]={"q":len(qs),"articles":len(index),"p50":dict(zip(MODES,np.median(mat,axis=0))),"p95":dict(zip(MODES,np.percentile(mat,95,axis=0))),
                     "ratios_pareto_full_range_pareto_pareto_top":eff(mat),"ci":np.percentile(draws,[2.5,97.5],axis=0).T.tolist()}
        costs[sub]={}
        for arm in MODES:
            allrows=[v["costs"][arm] for cur in preds.values() for c,v in cur.items() if c in conditions and (sub=="all" or c==sub)]
            x=np.asarray(allrows)
            costs[sub][arm]={k:{"sum":float(x[:,i].sum()),"p50":float(np.median(x[:,i])),"p95":float(np.percentile(x[:,i],95))}
                             for i,k in enumerate(m["cost_fields"])}
    sizes={"full":(old/"full.sqlite").stat().st_size,"pareto":(base/"pareto.sqlite").stat().st_size,"range2d":(base/"range.sqlite").stat().st_size,
           "top64":sum(f.stat().st_size for f in (old/"top64.sqlite",logs/"zip.sqlite",logs/"bounds.sqlite"))}
    totals=Counter()
    for v in build.values():totals.update(v)
    out={"size":sizes,"construction":dict(totals),"selection":{c:{"records":dict(Counter(selections[c])),"merged":dict(Counter(events[c]))} for c in conditions},
         "case_counts":{c:sum(preds[q][c]["answer"] is not None for q in preds) for c in conditions},"warm":clocks,"costs":costs,
         "strict":m["strict"],"latency_trials":m["timings"],"independent_questions":len(preds),"main_cases":len(preds)*6}
    save(D/"results.json",out)
    for k in ("size","construction","selection","case_counts"):print(k,out[k])
    for sub,v in clocks.items():print(sub,v["p50"],v["p95"])
    print(clocks["all"]["ratios_pareto_full_range_pareto_pareto_top"],clocks["all"]["ci"])
if __name__=="__main__":main()
