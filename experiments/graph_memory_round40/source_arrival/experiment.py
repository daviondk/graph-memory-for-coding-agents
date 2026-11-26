"""Benchmark exact incremental admission from fixed in-memory arrays of ISETrace nodes."""
from collections import Counter
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from time import perf_counter_ns

import numpy as np

D=Path(__file__).resolve().parent
R39=D.parents[1]/"graph_memory_round39"
BUDGET=2048
I32=np.ctypeslib.ndpointer(np.int32,ndim=1,flags="C_CONTIGUOUS")
I64=np.ctypeslib.ndpointer(np.int64,ndim=1,flags="C_CONTIGUOUS")
U8=np.ctypeslib.ndpointer(np.uint8,ndim=1,flags="C_CONTIGUOUS")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name,obj):
    data=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
    (D/name).write_bytes(gzip.compress(data,mtime=0) if name.endswith(".gz") else data)


class Planner:
    def __init__(self, cost, value, limit=BUDGET):
        libpath=os.environ.get("ADMISSION_LIBRARY") or D/("admit.dll" if os.name=="nt" else "admit.so")
        self.lib=ctypes.CDLL(str(libpath))
        self.lib.optimum.argtypes=[ctypes.c_int,ctypes.c_int,I32,I64,U8,I64]
        self.lib.optimum.restype=None
        self.lib.competitor.argtypes=[ctypes.c_int,ctypes.c_int,I32,I64,I64]
        self.lib.competitor.restype=ctypes.c_int64
        self.cost=np.asarray(cost,dtype=np.int32)
        self.value=np.asarray(value,dtype=np.int64)
        assert all(c>0 for c in cost) and all(u>=0 for u in value)
        assert sum(map(int,self.value)) < 2**63
        self.budget=limit

    def prefix(self,ids):
        cum=self.cost[ids].cumsum()
        k=int(np.searchsorted(cum,self.budget//2,side="right"))
        return ids[:k], self.budget-(int(cum[k-1]) if k else 0)

    def full(self,ids):
        head,cap=self.prefix(ids)
        tail=ids[len(head):]
        values=np.zeros(cap+1,dtype=np.int64)
        chosen=np.empty(len(tail),dtype=np.uint8)
        self.lib.optimum(len(tail),cap,self.cost[tail],self.value[tail],chosen,values)
        return tuple(np.concatenate([head,tail[chosen.astype(bool)]]).tolist()),head,values

    def update(self,cached,combined,added):
        packet,old_head,frontier=cached
        if not len(added):
            return packet,"no_open_candidate"
        head,cap=self.prefix(combined)
        if not np.array_equal(head,old_head):
            return self.full(combined)[0],"prefix"
        contender=self.lib.competitor(len(added),cap,self.cost[added],self.value[added],frontier)
        if contender < int(frontier[-1]):
            return packet,"strict_certificate"
        return self.full(combined)[0],"tie" if contender==int(frontier[-1]) else "better_tail"


def pool(db,q):
    rows=db.execute("SELECT id,tokens,utility FROM node WHERE q=? ORDER BY rank",(q,)).fetchall()
    rev={n:i for i,(n,_,_) in enumerate(rows)}
    refs=[set() for _ in rows]
    for n,source in db.execute("SELECT DISTINCT id,source FROM span WHERE q=?",(q,)):
        refs[rev[n]].add(source)
    assert all(refs)
    plan=Planner([r[1] for r in rows], [round(r[2]*2**32) for r in rows])
    return plan,refs


def cases(plan,refs,q,pct):
    sources=sorted(set.union(*refs),key=lambda s:sha(f"r40-availability|{q}|{s}".encode()))
    n=len(sources)*pct//100
    known=set(sources[:n])
    old=np.array([i for i,s in enumerate(refs) if s<=known],dtype=np.int32)
    t=perf_counter_ns()
    cache=plan.full(old)
    setup=perf_counter_ns()-t
    result=[]
    for source in sources[n:]:
        combined=np.array([i for i,s in enumerate(refs) if s<=known|{source}],dtype=np.int32)
        added=np.setdiff1d(combined,old,assume_unique=True)
        truth=plan.full(combined)[0]
        found,why=plan.update(cache,combined,added)
        assert found==truth
        times=[[],[]]
        for rep in range(3):
            rotation=(len(result)+rep)%2
            for arm in (rotation,1-rotation):
                t=perf_counter_ns()
                got=plan.update(cache,combined,added)[0] if arm else plan.full(combined)[0]
                times[arm].append(perf_counter_ns()-t)
                assert got==truth
        result.append(dict(source=source, added=len(added), mode=why, stable=truth==cache[0],
            before_size=len(cache[0]), after_size=len(truth), digest=sha(np.asarray(truth,dtype="<i4").tobytes()),
            full_ns=times[0], update_ns=times[1]))
    return dict(queries=result, setup_ns=setup,frontier_bytes=cache[2].nbytes,nodes=len(old))


def summary(z,pct):
    buckets=[z[q][str(pct)] for q in sorted(z)]
    groups=[row["queries"] for row in buckets]
    events=[r for g in groups for r in g]
    live=[r for r in events if r["added"]]
    agg=np.array([[sum(sum(r["full_ns"]) for r in g),sum(sum(r["update_ns"]) for r in g),
                   sum(r["mode"]=="strict_certificate" for r in g),sum(bool(r["added"]) for r in g)] for g in groups],dtype=np.int64)
    rng=np.random.default_rng(405301)
    bt=agg[rng.integers(0,len(groups),size=(10000,len(groups)))].sum(axis=1)
    interval=lambda a:np.quantile(a,[.025,.975]).tolist()
    return dict(queries=len(groups),events=len(events),with_candidates=len(live),modes=Counter(r["mode"] for r in events),
                stable=sum(r["stable"] for r in live),cache_rate=sum(r["mode"]=="strict_certificate" for r in live)/len(live),
                rate_ci=interval(bt[:,2]/bt[:,3]),time_ratio=agg[:,0].sum()/agg[:,1].sum(),ratio_ci=interval(bt[:,0]/bt[:,1]),
                frontier_bytes=[min(s["frontier_bytes"] for s in buckets),max(s["frontier_bytes"] for s in buckets)],
                median_setup_us=np.median([s["setup_ns"] for s in buckets])/1000,
                median_full_us=np.median([t for r in events for t in r["full_ns"]])/1000,
                median_update_us=np.median([t for r in events for t in r["update_ns"]])/1000)


def main():
    p=R39/"provenance_packet_demo/reader.sqlite"
    manifest=json.loads((p.parent/"manifest.json").read_bytes())
    assert sha(p.read_bytes())==manifest.get("files",manifest)["reader.sqlite"]
    db=sqlite3.connect(p.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    queries=[row[0] for row in db.execute("SELECT DISTINCT q FROM node ORDER BY q")]
    assert len(queries)==40
    rows={}
    for q in queries:
        planner,refs=pool(db,q)
        rows[q]={str(pct):cases(planner,refs,q,pct) for pct in (50,25,75)}
    save("outcomes.json.gz",rows)
    result={str(pct):summary(rows,pct) for pct in (50,25,75)}
    save("results.json",dict(groups=result,protocol=sha((D/"PROTOCOL_RU.md").read_bytes()),data=sha(p.read_bytes()),
                            output=sha((D/"outcomes.json.gz").read_bytes())))
    print(result)


if __name__=="__main__":
    main()

