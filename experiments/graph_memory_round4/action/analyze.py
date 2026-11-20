"""Paired cluster analyses and secondary cap sensitivity from the received packets."""
import collections
import itertools
import json
from pathlib import Path
import platform
import numpy as np
import brotli
from experiment import D,ALL,ARMS,FLAT,archive,decisions,choose,digest,post,read,rows,stats,write

BUDGETS=(512,1024,2048,4096)
ADAPT=("static_flat","adapt_flat","adapt_joint")
def avg(a):return float(np.mean(a))
def summarize(obs,features,panel):
    projects=sorted({r[1] for r in obs});ids=np.asarray([r[0] for r in obs]);labs=np.asarray([r[1] for r in obs]);groups=[labs==p for p in projects]
    group_n=np.array([sum(g) for g in groups])
    rng=np.random.default_rng(184296);inds=rng.integers(len(groups),size=(10000,len(groups)))
    denom=group_n[inds].sum(axis=1)
    signs=np.asarray(list(itertools.product((-1,1),repeat=len(projects))))
    names=(*ALL,*ADAPT)
    result={};out=collections.defaultdict(dict)
    all_m={}
    for arm in ARMS:
        rates={};vectors={}
        for mode in names:
            counts=np.asarray([r[4][arm][mode] for r in obs]);wire=counts[:,0];vectors[mode]=wire
            rates[mode]=dict(queries=len(wire),bytes=int(wire.sum()),mean=avg(wire),median=float(np.median(wire)),p95=float(np.quantile(wire,.95)),request_bytes=int(counts[:,1].sum()),reply_bytes=int(counts[:,2].sum()),
             blocks_offered=int(counts[:,3].sum()),blocks_confirmed=int(counts[:,4].sum()),output_rows_reused=int(counts[:,5].sum()),
             entire_response_within={n:int(sum(wire<=n)) for n in BUDGETS})
        effects={}
        for new,old in [("adapt_joint","full"),("adapt_joint","static_flat"),("adapt_joint","adapt_flat"),("adapt_joint","runs"),("joint","runs"),("epoch","runs"),("adapt_flat","static_flat")]:
            # Positive means fewer bytes with the new protocol, all interventions preserve return text.
            diff=vectors[old]-vectors[new];weights=np.asarray([diff[g].sum() for g in groups]);effect=weights.sum();rep=weights[inds].sum(axis=1)/denom
            effects[new+"-"+old]=dict(saved_bytes=int(effect),percent_saved=100*effect/vectors[old].sum(),bytes_per_query=avg(diff),ci_bytes=np.quantile(rep,[.025,.975]).tolist(),equal_issue_bytes=avg([diff[ids==i].mean() for i in set(ids)]),equal_project_bytes=avg(weights/group_n),
                faster=int(sum(diff>0)),slower=int(sum(diff<0)),tied=int(sum(diff==0)),two_sided_project_randomization=float(np.mean(np.abs(signs@weights)>=abs(effect))),
                per_project={p:[int(n),int(w)] for p,n,w in zip(projects,group_n,weights)})
        result[arm]={"methods":rates,"contrasts":effects};all_m[arm]=vectors
    compare={}
    for new,old in [('typed','lru'),('typed','point'),('point','lru')]:
        diff=all_m[old]['adapt_joint']-all_m[new]['adapt_joint']
        totals=np.asarray([diff[g].sum() for g in groups]);rep=totals[inds].sum(axis=1)/denom
        compare[new+'-'+old]={"saved_bytes":int(totals.sum()),"per_query":avg(diff),"ci":np.quantile(rep,[.025,.975]).tolist(),"better":int(sum(diff>0)),"worse":int(sum(diff<0))}
    return dict(queries=len(obs),projects=projects,issues=len(set(ids)),lines=int(sum(r[5] for r in obs)),methods=result,selected=features,writer_comparison=compare)
def main():
    model=read(D/"model.json")
    all_results={}
    for panel in ('A','B'):
        observed=[];dec=iter(rows(D/"decision_B.jsonl.gz")) if panel=="B" else None
        counts={a:{k:collections.Counter() for k in ADAPT} for a in ARMS}
        for r in stats(panel):
            iid,repo,t,feat,cost,nlines=r
            if dec is not None:
                di,dt,choice=next(dec);assert (di,dt)==(iid,t)
            else:
                choice={a:{"static_flat":choose(model,[],FLAT),"adapt_flat":choose(model,feat[a],FLAT),"adapt_joint":choose(model,feat[a],ALL)} for a in ARMS}
            for a,policy in choice.items():
                for k,v in policy.items():cost[a][k]=cost[a][v];counts[a][k][v]+=1
            observed.append(r)
        if dec is not None:assert next(dec,None) is None
        all_results[panel]=summarize(observed,counts,panel)
    out=dict(panels=all_results,python=platform.python_version(),brotli=brotli.__version__,exact_checks=sum(p["queries"]*len(ARMS)*len(ALL) for p in all_results.values()))
    write(D/"results.json",out)
    for p,v in all_results.items():
        print(p,v["queries"],v["issues"],v["lines"],v["selected"]["lru"])
        for a in ARMS:
            print(a,[(x,round(v["methods"][a]["methods"][x]["mean"],1)) for x in (*ALL,*ADAPT)])
        print(v["methods"]["lru"]["contrasts"]["adapt_joint-adapt_flat"])
if __name__=="__main__":main()
