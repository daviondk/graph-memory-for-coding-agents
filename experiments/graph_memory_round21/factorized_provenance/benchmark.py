"""Measure warmed SQLite loads plus feature extraction, and paired uncertainty."""
import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key]="1"
import collections
import gc
import hashlib
import platform
import sqlite3
import statistics
import time
import numpy as np
from study import D, CACHE, ref, save
from operators import load_flat, load_packed, flat_stats, packed_stats, rank_strength


def paired(f,p):
    rng=np.random.default_rng(21013)
    base=np.array(f,dtype=float); new=np.array(p,dtype=float)
    ids=rng.integers(len(base),size=(10000,len(base)))
    diff=new-base
    logs=np.log(new/base)
    return {"flat_median_ms":float(np.median(base)), "packed_median_ms":float(np.median(new)),
            "median_paired_delta_ms":float(np.median(diff)), "paired_delta_ci95_ms":np.quantile(np.median(diff[ids],axis=1),[.025,.975]).tolist(),
            "geomean_packed_over_flat":float(np.exp(logs.mean())), "ratio_ci95":np.exp(np.quantile(logs[ids].mean(axis=1),[.025,.975])).tolist(),
            "packed_faster_equal_slower":[int((diff<0).sum()),int((diff==0).sum()),int((diff>0).sum())]}


def main():
    lock=ref.read(D/"projection-lock.json")
    panel=ref.read(D/"timing-panel.json.gz")
    assert ref.sha(D/"timing-panel.json.gz")==lock["timing"] and len(panel)==128
    dbs={}
    for kind,record in lock["db"].items():
        p=CACHE/(kind+".sqlite")
        assert ref.sha(p)==record["sha256"]
        dbs[kind]=sqlite3.connect(p.as_uri()+"?mode=ro&immutable=1",uri=True)
        dbs[kind].execute("PRAGMA cache_size=-32768")
    cases=sorted(panel,key=lambda t:hashlib.sha256(("timing-order"+t).encode()).digest())
    strengths={t:rank_strength(np.array(panel[t]["order"])) for t in cases}
    rows=[]; reference={}
    for rep in range(-1,7):
        for pos,t in enumerate(cases if rep%2 else cases[::-1]):
            tid=panel[t]["tid"]
            for kind in (("flat","packed") if (pos+rep)%2 else ("packed","flat")):
                db=dbs[kind];strength=strengths[t]
                start=time.perf_counter_ns()
                if kind=="packed":
                    geom=load_packed(db,tid)
                    loaded=time.perf_counter_ns()
                    feat=packed_stats(geom,strength)
                else:
                    n,arcs=load_flat(db,tid)
                    loaded=time.perf_counter_ns()
                    feat=flat_stats(n,arcs,strength)
                end=time.perf_counter_ns()
                if rep<0:
                    if t in reference:
                        assert np.allclose(feat,reference.pop(t),rtol=0,atol=1e-10)
                    else:reference[t]=feat
                else:rows.append({"t":t,"kind":kind,"rep":rep,"load_ms":(loaded-start)/1e6,
                                   "compute_ms":(end-loaded)/1e6,"total_ms":(end-start)/1e6})
    assert not reference and len(rows)==128*7*2
    save(D/"paired-times.json.gz",rows)
    by=collections.defaultdict(list)
    for row in rows:by[row["t"],row["kind"]].append(row)
    effects={}
    for name in ("load_ms","compute_ms","total_ms"):
        p=[[statistics.median(r[name] for r in by[t,k]) for t in cases] for k in ("flat","packed")]
        effects[name]=paired(*p)
    trajectory=ref.read(D/"by-trajectory.json.gz");qs=ref.read(D/"by-query.json.gz")
    stats={key:sum(r[key] for r in trajectory) for key in ("n","edges","adjacent","links","groups")}
    stats["flat_rows"]=stats["n"]+stats["edges"]
    stats["packed_rows"]=stats["n"]+stats["adjacent"]+stats["links"]
    big=sorted(trajectory,key=lambda r:r["edges"]/max(1,r["adjacent"]+r["links"]),reverse=True)[0]
    plans={k:[] for k in dbs}
    for k,statements in {"flat":["SELECT COUNT(*) FROM node WHERE t=?","SELECT a,b,k FROM edge WHERE t=?"],
                          "packed":["SELECT g FROM node WHERE t=? ORDER BY n","SELECT a,b FROM adjacent WHERE t=?","SELECT a,b,k FROM link WHERE t=?"]}.items():
        for sql in statements:plans[k].append([r[3] for r in dbs[k].execute("EXPLAIN QUERY PLAN "+sql,(0,))])
    save(D/"results.json",{"timings":effects,"largest_expansion":big,"size":lock["db"],"tables":stats,
        "queries":len(qs),"trajectories":len(trajectory),"max_feature_error":max(r["error"] for r in qs),
        "matches":{p:sum(r["match"][p] for r in qs) for p in ("prefix","skip")},"plan":plans,
        "python":platform.python_version(),"sqlite":sqlite3.sqlite_version,"platform":platform.platform(),
        "cpu":platform.processor(),"numpy":np.__version__,"reps":7,"panel":128,"source":ref.sha(D/"projection-lock.json"),
        "timings_sha256":ref.sha(D/"paired-times.json.gz"),"benchmark_code":ref.sha(D/"benchmark.py")})
    print(stats,effects,flush=True)

if __name__=="__main__":
    main()
