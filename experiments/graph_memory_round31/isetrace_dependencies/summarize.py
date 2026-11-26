"""Summarize equally weighted held trajectories, retaining every pre-fixed contrast."""
from collections import defaultdict
import numpy as np
from prepare import D,save,read,sha

def main():
    plan=read(D/"plan.json");rows=read(D/"per-session.json.gz");cost=read(D/"construction-cost.json.gz");seal=read(D/"result-seal.json")
    times=read(D/"primary-sql.json.gz");stats={};lat={};structure={}
    for group in ("overlap3","overlap2","disjoint3"):
        ids=[q for q in plan["qids"] if plan["groups"][q]==group];stats[group]={};structure[group]={}
        for view in ("line_bm25","line_recency","block_bm25","block_recency"):
            stats[group][view]={};ts=[rows[q][view] for q in ids];groups={};rng=np.random.default_rng(31081);boots=rng.integers(len(ids),size=(10000,len(ids)))
            for name in ts[0]["counts"]:
                numbers={scope:np.asarray([r["counts"][name][scope] for r in ts],dtype=np.int64) for scope in ("sampled","single","exhaustive")}
                d={"cache_rows":sum(r["sizes"][name] for r in ts)}
                for scope,arr in numbers.items():d[scope]={**dict(zip(seal["fields"],arr.sum(axis=0).tolist())),"n":sum(r["cases"][scope] for r in ts)}
                groups[name]=d
            cons={}
            for k in (1,2,4,8,64):
                dst=f"mask_pareto{k}";vals=np.asarray([r["counts"][dst]["sampled"][0] for r in ts])
                for mode in ("raw","producer","atom_group","mask_group"):
                    diff=(vals-np.asarray([r["counts"][mode+str(k)]["sampled"][0] for r in ts]))/64.0
                    cons[f"mask_pareto{k}_vs_{mode}{k}"]={"certified_pp":float(100*diff.mean()),"ci":np.percentile(100*diff[boots].mean(axis=1),[2.5,97.5]).tolist(),
                        "wins_cases":int(sum(max(0,x) for x in diff*64)),"loss_cases":int(sum(max(0,-x) for x in diff*64))}
            stats[group][view]={"sessions":len(ids),"arms":groups,"contrasts":cons}
            structure[group][view]={f:sum(r[f] for r in ts) for f in ("candidates","unique_atoms","signatures","minimal","multiple_dependencies")}
            structure[group][view]["cases_with_strict_dominance"]=sum(r["minimal"]<r["signatures"] for r in ts)
            structure[group][view]["mask_ns"]=sum(cost[q][view]["mask_ns"] for q in ids)
            structure[group][view]["priority_ns"]=sum(cost[q][view]["priority_ns"] for q in ids)
            structure[group][view]["selection_ns"]=sum(cost[q][view]["selection_ns"] for q in ids)
    # Four repeated steps per fixture; repeated masks can be sampled naturally more than once within a small graph.
    by=defaultdict(list);calls=defaultdict(list)
    for rep,q,mask,m,ns,c in times:by[q,mask,m].append(ns/1e3);calls[m].append(c)
    for m in plan["modes"]:
        vals=[ns/1e3 for rep,q,mask,mode,ns,c in times if mode==m]
        lat[m]={"invocations":len(vals),"p50_us":float(np.median(vals)),"p95_us":float(np.percentile(vals,95)),"mean_sql_calls":float(np.mean(calls[m]))}
    output={"physical":seal["physical"],"groups":stats,"structural":structure,"primary_sql":lat,"exhaustive_validations":seal["exhaustive_case_validations"],
            "attainable_answer_checks":seal["exhaustive_rank_sets"],"inventory_sha":sha(D/"source-inventory.json.gz")}
    save(D/"results.json",output)
    print('structural',structure["overlap3"]["line_bm25"]);print('primary')
    for m in plan["modes"]:
        row=stats["overlap3"]["line_bm25"]["arms"][m+"4"];print(m,row['sampled'],row["cache_rows"],lat[m],seal["physical"][m+"4"]["bytes"])
    print('primary contrasts', {k:v for k,v in stats["overlap3"]["line_bm25"]["contrasts"].items() if k.startswith("mask_pareto4_")})
    print("strata",[(g,v,stats[g][v]["arms"]["mask_pareto4"]["sampled"]["certified"],stats[g][v]["arms"]["mask_group4"]["sampled"]["certified"],stats[g][v]["arms"]["producer4"]["sampled"]["certified"]) for g in stats for v in stats[g]])
if __name__=="__main__":main()
