"""Group question paired resource and coverage estimands, clustering primary uncertainty by article."""
from collections import Counter,defaultdict
import numpy as np
from build import sources
from inputs import D,read,save,sha

def main():
    p,cases,old,logs,base,dest=sources();built=read(D/"build-rows.json.gz");bs=read(D/"build-seal.json");rs=read(D/"result-seal.json")
    ans=read(D/"answers.json.gz");ev=read(D/"events.json.gz");times=read(D/"latency.json.gz");names=sorted(next(iter(next(iter(ans.values())).values()))["arms"])
    vm=defaultdict(list)
    for q,c,m,rep,ns in times:vm[q,c,m].append(ns/1e3)
    store={};common=(logs/"zip.sqlite").stat().st_size+(logs/"bounds.sqlite").stat().st_size;regbytes=bs["files"]["registry"]["bytes"]
    for n in names:
        count=sum(x["stores"][n]["kept"] for x in built.values());complete=sum(x["stores"][n]["complete"] for x in built.values())
        store[n]={"total_rows":count,"questions_fully_covered":complete,"cache_bytes":bs["files"][n]["bytes"],
                  "total_bytes":bs["files"][n]["bytes"]+regbytes+common}
    quantities={};effects={};cost={}
    for group in ("primary","primary/independent","primary/targeted","sampled","outside","outside/partial","outside/mixed"):
        items=[(q,c) for q,cs in ans.items() for c in cs if c.startswith(group+"/" if "/" not in group else group)]
        titles=sorted({ev[q]["article"] for q,c in items});blocks=[[i for i,(q,c) in enumerate(items) if ev[q]["article"]==t] for t in titles]
        truth=np.asarray([ans[q][c]["gold"] is None for q,c in items]);quantities[group]={"n":len(items),"articles":len(titles),"true_null":int(truth.sum())}
        vals={n:np.asarray([[0 if x is None else x for x in ans[q][c]["arms"][n]] for q,c in items]) for n in names}
        cost[group]={n:dict(zip(rs["fields"],vals[n].sum(axis=0).astype(int).tolist())) for n in names}
        if group in ("primary","sampled","outside"):
            rng=np.random.default_rng(30192);draws=rng.integers(len(titles),size=(10000,len(titles)));effects[group]={}
            for k in (8,64):
                mp=vals["mask_pareto"+str(k)]
                for a in ("raw","producer","mask_group","geometry","nms30"):
                    diff=mp[:,0]-vals[a+str(k)][:,0]
                    cl=np.array([diff[b].mean() for b in blocks]);dist=100*cl[draws].mean(axis=1)
                    effects[group][f"mask_pareto{k}_vs_{a}{k}"]={"certified_pp":float(100*diff.mean()),"ci":np.percentile(dist,[2.5,97.5]).tolist(),
                                                                 "wins":int((diff>0).sum()),"losses":int((diff<0).sum())}
    lat={}
    for n in [a for a in names if a.endswith("64")]:
        values=[np.median(v) for (q,c,m),v in vm.items() if m==n]
        lat[n]={"n":len(values),"p50":float(np.median(values)),"p95":float(np.percentile(values,95))}
    metadata={}
    for x in ("registry","distinct_masks","minimal_masks","producers","incidence_ns","group_and_pareto_ns","producer_ns"):
        ls=[d[x] for d in built.values()];metadata[x]={"sum":sum(ls),"min":min(ls),"median":float(np.median(ls)),"max":max(ls)}
    save(D/"results.json",{"storage":store,"common":common,"registry_bytes":regbytes,"structural":metadata,"outcomes":quantities,
                          "cost":cost,"contrasts":effects,"latency_us":lat,"strict":rs["strict"],"timing_n":rs["latency_samples"]})
    print("structural",metadata);print("sizes",store)
    for g in ("primary","sampled","outside"):
        print(g,quantities[g],{n:(x["certified"],x["certified_null"],x["correct_candidate_present"],x["windows"],x["blob_bytes"],x["naive_ignore_unknown_wrong"]) for n,x in cost[g].items()})
    print("p50,p95",lat)
if __name__=="__main__":main()
