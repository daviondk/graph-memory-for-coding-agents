"""Exhaustive one-source counterfactuals over frozen real queries, exact native knapsack control."""
import gzip
import json
import hashlib
import math
import platform
import sqlite3
import sys
import statistics
from time import perf_counter_ns
from serve import BUDGET,D,DEMO,Snapshot,selection,picker,np
ARMS=("full","certificate","late_boundary","selected_only")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(name,data):picker.save(D/name,data)
def run():
    engine=Snapshot(DEMO/"reader.sqlite");ref=json.loads((DEMO/"reference.json").read_bytes())
    qs=sorted(ref);assert len(qs)==40
    frozen={};base_costs={}
    for q in qs:
        p,barrier,compute_ns,build_ns=engine.prepare(q);assert list(p)==ref[q]["ids"]
        sources=[s[0] for s in engine.conn.execute("SELECT DISTINCT source FROM span WHERE q=? ORDER BY source",(q,))]
        frozen[q]=dict(packet=p,barrier=barrier,sources=sources)
        base_costs[q]=dict(full=compute_ns,overhead=build_ns)
    synthetic=[(0,2,1.),(1,9,.01),(2,3,.01),(3,8,10.)]
    before,barrier=selection(synthetic,10,engine.solve);after,_=selection([r for r in synthetic if r[0]!=1],10,engine.solve)
    assert before==(0,3) and barrier==1 and after==(0,2)
    put("schedule.json.gz",frozen);put("schedule-seal.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),code=sha(D/"experiment.py"),
        engine=sha(D/"serve.py"),frozen=sha(D/"schedule.json.gz"),projection=sha(DEMO/"reader.sqlite"),reference=sha(DEMO/"reference.json")))
    obs={}
    for j,q in enumerate(qs):
        items=[]
        for i,source in enumerate(frozen[q]["sources"]):
            outcomes={};timings={k:[] for k in ARMS};dirties={}
            for r in range(3):
                off=(r+i+j)%4
                for name in ARMS[off:]+ARMS[:off]:
                    start=perf_counter_ns();result,dirty=engine.result(q,source,name);dt=perf_counter_ns()-start
                    timings[name].append(dt)
                    if name in outcomes:assert outcomes[name]==result
                    else:outcomes[name]=result;dirties[name]=dirty
            assert outcomes["certificate"]==outcomes["late_boundary"]==outcomes["full"]
            wrong=outcomes["selected_only"]!=outcomes["full"]
            flag=engine.conn.execute("SELECT selected,barrier FROM dependency WHERE q=? AND source=?",(q,source)).fetchone() or (0,0)
            actual=outcomes["full"]
            items.append(dict(source=source,selected_dep=flag[0],barrier_dep=flag[1],changed=actual!=frozen[q]["packet"],wrong=wrong,
                full_packet=actual,timings=timings,needs=dirties))
        obs[q]=dict(build=base_costs[q],rows=items)
    put("observations.json.gz",obs)
    stats=aggregate(obs)
    put("results.json",dict(**stats,seal=sha(D/"schedule-seal.json"),observations=sha(D/"observations.json.gz"),sqlite=sqlite3.sqlite_version,
        python=sys.version.split()[0],platform=platform.platform(),synthetic=dict(before=before,barrier=barrier,after=after)))
    print(stats)
def aggregate(obs):
    rows=[r for v in obs.values() for r in v["rows"]]
    times={k:np.asarray([t for r in rows for t in r["timings"][k]])/1000 for k in ARMS}
    hits=np.array([sum(not r["needs"]["certificate"] for r in v["rows"]) for v in obs.values()])
    size=np.array([len(v["rows"]) for v in obs.values()])
    per=np.asarray([[sum(sum(r["timings"][arm]) for r in v["rows"])/3 for arm in ("full","certificate")] for v in obs.values()])
    rng=np.random.default_rng(39119);draw=rng.integers(len(size),size=(10000,len(size)))
    speeds=per[draw].sum(axis=1);speed=speeds[:,0]/speeds[:,1]
    overhead=sum(v["build"]["overhead"] for v in obs.values());saved=per[:,0].sum()-per[:,1].sum()
    return dict(queries=len(obs),sources=len(rows),changed=sum(v["changed"] for v in rows),unsafe_false_hits=sum(v["wrong"] for v in rows),
      boundary_only=sum(not v["selected_dep"] and v["barrier_dep"] for v in rows),exact_cached=int(hits.sum()),
      macro_cache_rate=float(np.mean(hits/size)),macro_cache_ci=np.quantile((hits/size)[draw].mean(axis=1),[.025,.975]).tolist(),
      micro_cache_rate=hits.sum()/size.sum(),full_vs_cert_ratio=per[:,0].sum()/per[:,1].sum(),cluster_ratio_ci=np.quantile(speed,[.025,.975]).tolist(),
      median_and_p95_us={k:np.quantile(a,[.5,.95]).tolist() for k,a in times.items()},
      mean_extra_build_us=overhead/len(obs)/1000,mean_single_saving_us=saved/len(rows)/1000,
      workload_break_even_requests_per_query=(overhead/len(obs))/(saved/len(rows)) if saved>0 else None,
      each_arm_executions=len(rows)*3,dp_calls_per_arm={k:sum(r["needs"][k] for r in rows)*3 for k in ARMS})
if __name__=="__main__":run()

