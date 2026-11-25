"""Analyze fixed crossed queries and scenarios with cluster uncertainty by source article."""
from collections import defaultdict
import json
import numpy as np
from control import D,PAR,plan,ARMS,PRIMARY,read,save,sha

def summarize_values(a):
    x=np.asarray(a)
    return dict(mean=float(x.mean()),p50=float(np.median(x)),p95=float(np.quantile(x,.95)),maximum=float(x.max()))

def main():
    p,cases,_,old,new=plan();b=read(D/"build-seal.json");m=read(D/"measurement-seal.json");parent=read(PAR/"results.json")
    assert m["costs"]==sha(D/"validation-costs.json.gz") and m["latency"]==sha(D/"latency.json.gz")
    counts=read(D/"validation-costs.json.gz");times=read(D/"latency.json.gz");win=read(D/"window-build.json.gz")
    fields=("sql_calls","blob_bytes","recomputed_windows","bound_rows","fallback")
    costs={}
    for arm in ARMS:
        costs[arm]={}
        for subset in ("all","winner","record","random"):
            tab=[row[arm] for qs in counts.values() for name,row in qs.items() if subset=="all" or subset==name]
            arr=np.asarray(tab)
            costs[arm][subset]={f:{**summarize_values(arr[:,j]),"total":int(arr[:,j].sum())} for j,f in enumerate(fields)}
    totals={n:v["bytes"] for n,v in b["files"].items()}
    totals.update({n:parent["db"][n]["total_bytes"] for n in ("sky","top8","top64")})
    size={}
    for arm in ARMS:
        terms=arm.split("-")
        size[arm]=totals[terms[0]]
        if len(terms)==3:size[arm]+=totals["top"+terms[1]]
        if terms[-1] in ("local","bound"):size[arm]+=totals["bounds"]
    samples=defaultdict(list)
    for _,q,c,arm,ns in times:samples[q,c,arm].append(ns/1e3)
    keys=sorted((q,c) for q,c,arm in samples if arm=="sky");labels=sorted({cases[q]["title"] for q,c in keys})
    groups=[[i for i,(q,c) in enumerate(keys) if cases[q]["title"]==t] for t in labels]
    mat=np.array([[np.median(samples[q,c,arm]) for arm in ARMS] for q,c in keys])
    timing={}
    for j,arm in enumerate(ARMS):
        timing[arm]={}
        for c in ("all","winner","record","random"):
            ids=[i for i,(_,name) in enumerate(keys) if c=="all" or c==name]
            timing[arm][c]=summarize_values(mat[ids,j])
    rng=np.random.default_rng(28297);res=[];col=ARMS.index(PRIMARY)
    for draw in rng.integers(len(labels),size=(10000,len(labels))):
        selected=mat[np.concatenate([groups[g] for g in draw])]
        res.append([np.median(selected[:,0]-selected[:,col]),np.median(selected[:,0])/np.median(selected[:,col])])
    ci=np.percentile(res,[2.5,97.5],axis=0).T.tolist()
    sums=np.asarray([r[2:] for r in win],dtype=np.int64).sum(axis=0).tolist()
    names=("blob_bytes","zblob_bytes","read_pack_ns","compress_ns","upper_bound_ns","raw_insert_ns","zip_insert_ns","bounds_insert_ns")
    result={"strict_comparisons":m["strict"],"conditions":m["strict"]//len(ARMS),"latency_measurements":len(times),
            "questions":len(p["qids"]),"windows":len(win),"db":totals,"storage_per_arm":size,"build":dict(zip(names,sums)),
            "costs":costs,"latency_median_over_queries_us":timing,
            "primary":{"case":PRIMARY,"sky_minus_case_us":float(np.median(mat[:,0]-mat[:,col])),
                       "difference_ci":ci[0],"sky_over_case":float(np.median(mat[:,0])/np.median(mat[:,col])),"ratio_ci":ci[1]}}
    save(D/"results.json",result)
    print(json.dumps({"build":result["build"],"primary":result["primary"],"size":size,
        "main":{a:{"p50us":round(timing[a]["all"]["p50"],1),"p95us":round(timing[a]["all"]["p95"],1),
                   "blob":costs[a]["all"]["blob_bytes"]["total"],"windows":costs[a]["all"]["recomputed_windows"]["total"]} for a in ARMS}},indent=2))
if __name__=="__main__":main()
