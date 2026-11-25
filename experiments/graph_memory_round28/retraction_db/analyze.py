"""Verify strict answers against a second implementation; summarize costs by article."""
from collections import Counter, defaultdict
from pathlib import Path
import json
import numpy as np
from design import HERE,UP,read,sha,save
from study import NAMES,prepared,pack,connect

def describe(xs):
    a=np.asarray(xs)
    return {k:float(v) for k,v in zip(("mean","p50","p95","max"),(np.mean(a),*np.percentile(a,[50,95]),np.max(a)))}

def analyze():
    plan,cases,_,folder=prepared();cap=read(UP/"decision-seal.json")
    assert cap["decisions"]==sha(UP/"decisions.json.gz")
    primary=read(UP/"decisions.json.gz");refs=read(HERE/"reference.json.gz")
    info=read(HERE/"build-rows.json.gz");data=read(HERE/"measurements.json.gz");built=read(HERE/"build-seal.json")
    assert read(HERE/"measurement-seal.json")["data"]==sha(HERE/"measurements.json.gz")
    cross=0
    for q in plan["qids"]:
        assert info[q]["n"]==primary[q]["candidates"]
        assert [info[q]["front"][x] for x in ("pre","suf")]==primary[q]["frontiers"]
        for c,r in primary[q]["projections"].items():
            assert refs[q][c]["ban"]==r["cut"] and refs[q][c]["rank"]==r["rank"]
            assert pack(r["answer"])==pack(refs[q][c]["answer"])
            cross+=1
    db=connect(folder,False)
    checks={}
    for f in NAMES:
        schema="main" if f=="full" else f
        assert db.execute(f"PRAGMA {schema}.integrity_check").fetchone()==("ok",)
        entries=[db.execute(f"SELECT COUNT(*) FROM {schema}."+t).fetchone()[0] for t in (("pre","suf") if f=="sky" else ("r",))]
        pages=db.execute(f"PRAGMA {schema}.page_count").fetchone()[0]
        page_size=db.execute(f"PRAGMA {schema}.page_size").fetchone()[0]
        fpath=folder/(f+".sqlite")
        assert sha(fpath)==built["databases"][f]["sha256"] and pages*page_size==fpath.stat().st_size
        checks[f]={"pages":pages,"page_size":page_size,"total_bytes":fpath.stat().st_size,"standalone_entries":sum(entries),
                   "individual_tables":entries}
    db.close()
    build_times=Counter()
    for v in info.values():build_times.update(v["build"])
    for m in ("top8","top64"):
        checks[m]["total_with_fallback"]=checks[m]["total_bytes"]+checks["full"]["total_bytes"]
    regular={}
    for m,arms in data["regular"].items():
        regular[m]={}
        for c,vs in [*arms.items(),("all",[r for rows in arms.values() for r in rows])]:
            regular[m][c]={"n":len(vs),"fallback":sum(t["fallback"] for t in vs),"sqlite_calls":sum(t["calls"] for t in vs),
                "result_bytes":sum(t["app_bytes"] for t in vs),"with_null_marker":sum(t["transfer"] for t in vs),
                "sorted_candidates_visited":describe([t["rank_visited"] for t in vs])}
    grouped=defaultdict(list)
    for rep,q,c,m,ns in data["samples"]:
        grouped[q,c,m].append(ns/1e3)
    cohorts={}
    for c_filter in ("all","winner","record","random"):
        items=sorted((q,c) for q,c,m in grouped if m=="full" and (c_filter=="all" or c==c_filter))
        labels=sorted({info[q]["article"] for q,c in items})
        block=[[i for i,(q,c) in enumerate(items) if info[q]["article"]==art] for art in labels]
        mat=np.array([[np.median(grouped[q,c,m]) for m in NAMES] for q,c in items])
        rng=np.random.default_rng(28196)
        res=[]
        for draw in rng.integers(len(labels),size=(10000,len(labels))):
            ids=np.concatenate([block[j] for j in draw])
            selected=mat[ids]
            res.append([np.median(selected[:,1]-selected[:,0]),np.median(selected[:,1])/np.median(selected[:,0])])
        interval=np.percentile(res,[2.5,97.5],axis=0).T.tolist()
        cohorts[c_filter]={"tasks":len(items),"articles":len(labels),
            "query_median_us":{m:describe(mat[:,i]) for i,m in enumerate(NAMES)},
            "all_timing_us":{m:describe([x for q,c in items for x in grouped[q,c,m]]) for m in NAMES},
            "sky_minus_full_median_paired_us":float(np.median(mat[:,1]-mat[:,0])),
            "sky_over_full_ratio_of_medians":float(np.median(mat[:,1])/np.median(mat[:,0])),
            "difference_ci_article":interval[0],"ratio_ci_article":interval[1]}
    results={"questions":len(info),"articles":len(set(v["article"] for v in info.values())),
        "cross_checked_upstream":cross,"validated_queries":data["validations"]//len(NAMES),
        "strict_comparisons":data["validations"],"db":checks,"build_seconds":{k:t/1e9 for k,t in build_times.items()},
        "queries":regular,"timings":cohorts,"samples":len(data["samples"]),"sqlite_plans":data["plans"]}
    save(HERE/"results.json",results)
    print(json.dumps({"db":checks,"case_overall":regular["top8"]["all"],"timing":cohorts["all"],"build":results["build_seconds"]},indent=2))
if __name__=="__main__":analyze()
