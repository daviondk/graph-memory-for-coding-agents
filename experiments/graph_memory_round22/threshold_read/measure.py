"""Paired ISETrace operator measurements after materialized Dense ranks."""
from collections import Counter,defaultdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
import platform
import random
import statistics
import time

from operators import np,index,read,suffix_bounds
from check_edges import METHODS

HERE=Path(__file__).resolve().parent
def load(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)
def put(path,value):
    b=json.dumps(value,allow_nan=False,sort_keys=True,separators=(",",":")).encode()+b"\n"
    if path.suffix==".gz":b=gzip.compress(b,mtime=0)
    path.write_bytes(b)
def sha(p):return sha256(p.read_bytes()).hexdigest()
def select(ids):return set(sorted(ids,key=lambda q:sha256(("threshold-timing|"+q).encode()).digest())[:256])
def fp(ids):return sha256(np.asarray(ids,dtype="<i8").tobytes()).hexdigest()

def run():
    source=load(HERE/"inputs.json")
    data=[];by={};preps=[]
    for filename,rec in sorted(source["shards"].items()):
        path=HERE/filename;assert sha(path)==rec["sha"]
        for raw in load(path):
            p=np.asarray(raw["prior"]);c=np.asarray(raw["costs"]);signal=np.asarray(raw["signal"])
            start=time.perf_counter_ns();idx=index(p,c);mid=time.perf_counter_ns();upper=suffix_bounds(signal);end=time.perf_counter_ns()
            # These indexes exclude the shared float prior and integer cost columns.
            preps.append({"t":raw["t"],"n":len(p),"indexes_ns":mid-start,"suffix_ns":end-mid,"static_index_bytes":sum(v.nbytes for v in (idx.by_prior,idx.sorted_priors,idx.by_cost,idx.sorted_costs)),"suffix_bytes":upper.nbytes,"monotone":bool(np.all(signal[:-1]>=signal[1:]))})
            for q in raw["queries"]:
                assert q["q"] not in by
                by[q["q"]]=(raw["t"],np.asarray(q["order"],dtype=int),signal,upper,idx,q["expected"])
    assert len(by)==2000 and len(preps)==1207
    panel=select(by);save_times=[]
    rng=random.Random(31013)
    for q in sorted(by):
        t,o,s,u,ix,exp=by[q];record={"q":q,"t":t,"n":len(o),"arms":{}}
        for pol in ("prefix","skip"):
            counts={}
            for method in METHODS:
                got,count=read(method,o,s,u,ix,2048,pol)
                assert got==exp[pol],(q,pol,method,len(got),len(exp[pol]))
                counts[method]=count
            record["arms"][pol]={"expect_hash":fp(exp[pol]),"nodes":len(exp[pol]),"tokens":sum(int(ix.costs[x]) for x in exp[pol]),"counts":counts}
        data.append(record)
        if q not in panel:continue
        # All arms completed a warmup above. Timed blocks retain raw measurement order.
        for rep in range(7):
            arms=[(pol,method) for pol in ("prefix","skip") for method in METHODS]
            rng.shuffle(arms);ticks={}
            for pol,method in arms:
                start=time.perf_counter_ns();got,_=read(method,o,s,u,ix,2048,pol);end=time.perf_counter_ns()
                assert got==exp[pol]
                ticks[pol+"/"+method]=end-start
            start=time.perf_counter_ns();reverse=np.empty(len(o),dtype=int);reverse[o]=np.arange(len(o));end=time.perf_counter_ns()
            tick=end-start;start=time.perf_counter_ns();end=time.perf_counter_ns()
            save_times.append({"q":q,"t":t,"rep":rep,"ns":ticks,"order":["/".join(v) for v in arms],"inverse_ns":tick,"noop_ns":end-start})
    put(HERE/"per-query.json.gz",data);put(HERE/"timings.json.gz",save_times);put(HERE/"preparation.json.gz",preps)
    put(HERE/"measurement-seal.json",{"files":{n:sha(HERE/n) for n in ("per-query.json.gz","timings.json.gz","preparation.json.gz","operators.py","check_edges.py","edge-cases.json","measure.py","inputs.json","PROTOCOL_RU.md")},
        "panel_q":sorted(panel),"clock":"perf_counter_ns","python":platform.python_version(),"numpy":np.__version__,"device":"CPU, single Python thread; precomputed float64 scores and int64 costs",
        "cpu":platform.processor(),"warmups":1,"reps":7,"zero_timer":True,"seed":31013,"budget":2048})
    print("All 16000 native ordered selections matched. Timed",len(save_times),"query-repetition blocks.")


def boot_ratio(rows,policy,method):
    grouped=defaultdict(list)
    for q,row in rows.items():grouped[row["t"]].append([row[policy+"/"+method],row[policy+"/vector"]])
    vals=[grouped[t] for t in sorted(grouped)]
    rng=np.random.default_rng(13);sim=[]
    width=max(map(len,vals))
    table=np.full((len(vals),width,2),np.nan)
    for j,pair in enumerate(vals):table[j,:len(pair)]=pair
    for _ in range(100):
        ix=rng.integers(len(vals),size=(100,len(vals)))
        obs=table[ix].reshape(100,-1,2)
        med=np.nanmedian(obs,axis=1)
        sim.extend(med[:,0]/med[:,1])
    return np.quantile(sim,[.025,.975]).tolist()


def stats():
    seal=load(HERE/"measurement-seal.json");assert all(sha(HERE/n)==h for n,h in seal["files"].items())
    measurements=load(HERE/"timings.json.gz");counts=load(HERE/"per-query.json.gz");prep=load(HERE/"preparation.json.gz")
    readings=defaultdict(list)
    for r in measurements:readings[r["q"]].append(r)
    summary={}
    for q,rs in readings.items():
        keys=list(rs[0]["ns"]);summary[q]={"t":rs[0]["t"],**{k:statistics.median(r["ns"][k] for r in rs) for k in keys}}
    groups={}
    for pol in ("prefix","skip"):
        groups[pol]={}
        for m in METHODS:
            a=[r["arms"][pol]["counts"][m] for r in counts]
            tot={k:sum(x[k] for x in a) for k in a[0]}
            us=[v[pol+"/"+m]/1000 for v in summary.values()];vr=[v[pol+"/vector"]/1000 for v in summary.values()]
            frac=[x["scored"]/r["n"] for x,r in zip(a,counts,strict=True)]
            groups[pol][m]={"n":len(counts),"sum":tot,"micro_scored_fraction":tot["scored"]/sum(r["n"] for r in counts),"macro_scored_fraction":float(np.mean(frac)),
                "median_scored_fraction":float(np.median(frac)),"p95_scored_fraction":float(np.quantile(frac,.95)),"early":sum(f<1 for f in frac),
                "median_us":float(np.median(us)),"p95_us":float(np.quantile(us,.95)),"ratio_of_medians":float(np.median(us)/np.median(vr)),
                "ratio_ci":boot_ratio(summary,pol,m) if m!="vector" else [1.,1.]}
    n=sum(v["n"] for v in counts)
    out={"questions":len(counts),"trajectories":len(prep),"ranked_pu_query_pairs":n,"timing_questions":len(summary),"timing_trajectories":len({v["t"] for v in summary.values()}),
       "comparisons":len(counts)*len(METHODS)*2,"operator":groups,"clock_median_ns":statistics.median(v["noop_ns"] for v in measurements),
       "inverse_median_us":statistics.median(v["inverse_ns"] for v in measurements)/1000,"static_index_bytes":sum(v["static_index_bytes"] for v in prep),
       "suffix_bytes":sum(v["suffix_bytes"] for v in prep),"static_index_median_us":statistics.median(v["indexes_ns"] for v in prep)/1000,
       "suffix_median_us":statistics.median(v["suffix_ns"] for v in prep)/1000,"monotone_sources":sum(v["monotone"] for v in prep),"seal":sha(HERE/"measurement-seal.json")}
    put(HERE/"results.json",out)


if __name__=="__main__":
    import sys
    {"measure":run,"stats":stats}[sys.argv[1]]()

