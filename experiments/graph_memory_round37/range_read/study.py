"""Freeze query outputs before verification and time four range readers in paired blocks."""
import hashlib,itertools,json,gzip,os,platform,random,sqlite3,statistics,sys,tempfile,time
from pathlib import Path
from query import D,STORE,SQL,ARMS,build,read
from inputs import get,put,sha
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np

def encode(pairs):
    return [[n,s.hex()] for n,s in pairs]

def inputs():
    source=get(STORE/"prefix_inputs.json.gz")
    aggregate={}
    for i,(q,v) in enumerate(sorted(source.items())):
        aggregate[i]=dict(v,q=q,base=[(n,bytes.fromhex(s)) for n,s in v["base"]],
                            receipt={n:bytes.fromhex(s) for n,s in v["receipt"]})
    return aggregate

def timing(dbs,items,queries,qindex,panel):
    selected=[qindex[q] for q in panel]
    counts={e:{a:[] for a in ARMS} for e in selected}
    trial=list(itertools.permutations(ARMS))
    rng=random.Random(37116)
    rng.shuffle(trial)
    for order in trial:
        keys=list(selected)
        rng.shuffle(keys)
        for e in keys:
            item=items[e]
            lo,hi=queries[e]
            for arm in order:
                begin=time.perf_counter_ns()
                for _ in range(5):
                    read(dbs,arm,e,item,lo,hi)
                counts[e][arm].append((time.perf_counter_ns()-begin)/5)
    return {items[e]["q"]:{a:v for a,v in arms.items()} for e,arms in counts.items()}

def benchmark():
    items=inputs()
    tmpdir=Path("D:/CodexResearch/x20-r37-editor-deps").parent
    assert len(items)==1282
    with tempfile.TemporaryDirectory(dir=tmpdir) as tmp:
        dbs=build([Path(tmp)/"ready.sqlite",Path(tmp)/"lazy.sqlite"],items)
        try:
            # Only consult the client's next request extent after the store has been built.
            observed=get(D.parent/"code_visibility/observations.json.gz")
            queries={e:(min(n for n,_ in observed[v["q"]]["observed"]),max(n for n,_ in observed[v["q"]]["observed"])) for e,v in items.items()}
            plans=[x[-1] for x in dbs[1].execute("EXPLAIN QUERY PLAN "+SQL,(0,1,99))]
            assert sum("n>?" in node and "n<?" in node for node in plans)>=3,plans
            out={}
            for e,item in items.items():
                lo,hi=queries[e]
                arms={}
                for a in ARMS:
                    values,raw=read(dbs,a,e,item,lo,hi)
                    arms[a]=dict(answer=encode(values),returned=raw)
                crowded=bool(dbs[1].execute("SELECT overflow FROM v WHERE e=?",(e,)).fetchone()[0])
                out[item["q"]]=dict(issue=item["issue"],zone=item["zone"],range=[lo,hi],crowded=crowded,arms=arms)
            put(D/"forecasts.json.gz",out)
            # Confirm eligibility of partial pushdown on synthetic over-cap and disjoint cases in verify.py.
            panel=get(STORE/"plan.json")["panel"]
            samples=timing(dbs,items,queries,{v["q"]:e for e,v in items.items()},panel)
            put(D/"timings.json.gz",samples)
            environ=dict(sqlite=sqlite3.sqlite_version,os=platform.platform(),python=sys.version,query_plan=plans,wal="NORMAL",
                         timing="all 24 permutations; mean ns of five executions per block; medians per episode")
            put(D/"seal.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),operator=sha(D/"query.py"),benchmark=sha(D/"study.py"),
                outputs=sha(D/"forecasts.json.gz"),timings=sha(D/"timings.json.gz"),prior=sha(STORE/"manifest.json"),environment=environ))
        finally:
            for db in dbs:db.close()

def summarize():
    out=get(D/"forecasts.json.gz")
    ref=get(STORE/"reference.json.gz")
    seal=get(D/"seal.json")
    assert seal["outputs"]==sha(D/"forecasts.json.gz") and seal["timings"]==sha(D/"timings.json.gz")
    counts={a:0 for a in ARMS}
    for q,v in out.items():
        lo,hi=v["range"]
        target=[pair for pair in ref[q] if lo<=pair[0]<=hi]
        for arm,record in v["arms"].items():
            assert record["answer"]==target,(q,arm)
            counts[arm]+=record["returned"]
    raw=get(D/"timings.json.gz")
    qs=sorted(raw)
    values=np.array([[statistics.median(raw[q][a])/1000 for a in ARMS] for q in qs])
    ts,idx=np.unique([out[q]["issue"] for q in qs],return_inverse=True)
    agg=np.zeros((len(ts),4));np.add.at(agg,idx,values)
    rng=np.random.default_rng(37116)
    ratios={}
    pairs=[("inverse","lazy_full"),("inverse","eager_index"),("eager_index","eager_full")]
    # Ratio of episode-weighted means, with entire issues resampled in pairs.
    sample=rng.integers(len(ts),size=(10000,len(ts)))
    boots=agg[sample].sum(axis=1)
    for a,b in pairs:
        j,h=ARMS.index(a),ARMS.index(b)
        ratios[a+" / "+b]=dict(value=float(values[:,j].sum()/values[:,h].sum()),ci95=np.quantile(boots[:,j]/boots[:,h],[.025,.975]).tolist())
    total=sum(len(v["arms"]["inverse"]["answer"]) for v in out.values())
    summary=dict(episodes=len(out),issues=len({v["issue"] for v in out.values()}),overflow=sum(v["crowded"] for v in out.values()),
                 nonempty=sum(bool(v["arms"]["inverse"]["answer"]) for v in out.values()),answer_rows=total,db_returned=counts,
                 mean_us=dict(zip(ARMS,values.mean(axis=0))),paired_ratio=ratios,timed=len(qs),timed_issues=len(ts),
                 protocol=sha(D/"PROTOCOL_RU.md"),seal=sha(D/"seal.json"))
    put(D/"results.json",summary)
    print(json.dumps(summary,indent=1))
if __name__=="__main__":
    benchmark()
    summarize()

