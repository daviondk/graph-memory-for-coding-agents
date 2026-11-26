"""Count real SQLite index reads and verify every committed ranking and historical packet."""
import argparse
from collections import Counter, deque
import gzip
import hashlib
from itertools import product
import json
from pathlib import Path
import sqlite3
import tempfile

import numpy as np
from reserve_store import HERE, InstrumentedCutoff, ReserveStore, advance, refresh, key
from core import KS, M, NOW, OLD, connect, read
from bench import oracle

PLANS = [(m,l) for l in (8,9,12,16) for m in ("lazy","eager")]
PLANS = [("index",8), ("boundary",8)] + PLANS
COLS = ("warm_probes","warm_rows","cold_probes","cold_rows","score_rows","pairs","has_bound")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def encode(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",",":"), allow_nan=False).encode() + b"\n"


def save(name,v):
    data = encode(v)
    (HERE/name).write_bytes(gzip.compress(data,mtime=0) if name.endswith(".gz") else data)


def registration():
    paths = [HERE/"PROTOCOL_RU.md", HERE/"run.py", HERE/"reserve_store.py",
             HERE.parent/"cutoff"/"cutoff_store.py", HERE.parent/"cutoff"/"correctness.json",
             HERE.parent/"multi_read"/"core.py", HERE.parent/"multi_read"/"bench.py", OLD/"workload.json.gz"]
    import os
    return {os.path.relpath(p,HERE).replace("\\","/"):sha(p) for p in paths}


def check_state(state, actual, required, capacity):
    cached, bound = state
    assert len(cached) <= capacity
    assert list(cached) == sorted(cached, key=key, reverse=True)
    assert dict(cached).items() <= dict(actual).items()
    assert list(cached[:required]) == actual[:required], (state,actual,required)
    outside = [v for v in actual if v[0] not in dict(cached)]
    assert not outside or bound is not None and key(outside[0]) <= bound


def finite():
    out = {}
    all_scores = list(product((-1,0,1),repeat=3))
    for k,l in ((1,1),(1,2),(2,2),(2,3)):
        for mode in ("eager","lazy"):
            req = l if mode=="eager" else k
            start = ((-1,-1,-1),((),None))
            waiting,seen,counts = deque([start]),{start},Counter()
            while waiting:
                scores,state = waiting.popleft()
                for after in all_scores:
                    changes={i:(None if b<0 else b) for i,(a,b) in enumerate(zip(scores,after)) if a!=b}
                    actual=sorted([(i,s) for i,s in enumerate(after) if s>=0],key=key,reverse=True)
                    nxt = advance(state,changes,l,req)
                    counts["fallback" if nxt is None else "certified"] += 1
                    counts["with_removed_object"] += any(v is None for v in changes.values())
                    if nxt is None:
                        nxt = refresh(actual[:l], l)
                    check_state(nxt,actual,req,l)
                    future = (after,nxt)
                    if future not in seen:
                        waiting.append(future)
                        seen.add(future)
            out[f"{mode}-k{k}-L{l}"]=dict(**counts,reachable_states=len(seen))
    return out


def make(db, name, l, create=True):
    if name in ("index","boundary"):
        return InstrumentedCutoff(db, name, create)
    return ReserveStore(db,l,name,create)


def replay(path, name, l, work, refs):
    db = connect(path)
    try:
        store = make(db,name,l)
        per = {}
        max_cached = 0
        explain = db.execute("EXPLAIN QUERY PLAN "+NOW, ("q11",l)).fetchall()
        assert any("COVERING INDEX source_best" in r[-1] for r in explain)
        for q, rows in work.items():
            for row in rows:
                trace = []
                if isinstance(store, ReserveStore):
                    db.set_trace_callback(trace.append)
                assert store.update(q,row)
                db.set_trace_callback(None)
                e = dict(store.event)
                if isinstance(store, ReserveStore):
                    assert sum("SELECT CID,SCORE FROM SOURCE" in t.upper() for t in trace) == e.get("warm_probes",0)+e.get("cold_probes",0)
                    assert sum(" RETURNING SCORE" in t.upper() for t in trace) == e.get("score_rows",0)
                t = row["t"]
                actual = db.execute("SELECT cid,score FROM source WHERE q=? ORDER BY score DESC,cid", (q,)).fetchall()
                assert actual[:M] == refs[q][t]
                if isinstance(store, ReserveStore):
                    state = store.last[q][1]
                    check_state(state, actual, M if name=="lazy" else l, l)
                    max_cached = max(max_cached, sum(len(v[1][0]) for v in store.last.values()))
                else:
                    assert store.last[q][1] == actual[:M]
                    max_cached = max(max_cached, sum(len(v[1]) for v in store.last.values()))
                per[f"{q}/{t}"] = [int(e.get(k,0)) for k in COLS]
        for q, versions in refs.items():
            for t, ranking in enumerate(versions):
                for k in KS:
                    assert store.get(q,t,k) == ranking[:k]
                    assert store._history(q,t,k) == ranking[:k]
        packet=[(q,j,t,x.hex()) for q,j,t,x in db.execute("SELECT q,part,rev,payload FROM packet ORDER BY q,part,rev")]
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        totals = dict(zip(COLS,map(int,np.array(list(per.values())).sum(0))))
        totals.update(mean_pairs=totals["pairs"]/len(per),max_pairs=max(x[5] for x in per.values()),max_all_queries_pairs=max_cached,
                      snapshot_rows=len(packet),snapshot_hash=hashlib.sha256(encode(packet)).hexdigest(),
                      query_plan=[r[-1] for r in explain])
        return per,totals
    finally:
        db.close()


def restart(path, name, l, work, refs):
    a,b=connect(path),connect(path)
    try:
        pair=[make(a,name,l),make(b,name,l,False)]
        q="q11"
        for t,row in enumerate(work[q],1):
            s,other=pair[t%2],pair[(t+1)%2]
            if t%5==0:
                s.last.clear()
            if t==17:
                prior=dict(s.last)
                try:
                    s.update(q,row,fault=True)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("failed rollback")
                assert s.last==prior
                assert other.get(q,t-1,8) == refs[q][t-1]
                try:
                    other.get(q,t,8)
                except ValueError:
                    pass
                else:
                    raise AssertionError("uncommitted state was visible")
            assert s.update(q,row)
            assert not s.update(q,row)
            assert s._history(q,t,8)==refs[q][t]
        for bad in [dict(row,sha="conflict"),dict(row,t=t+2)]:
            try:
                s.update(q,bad)
            except ValueError:
                pass
            else:
                raise AssertionError("bad replay or revision gap accepted")
        return len(work[q])
    finally:
        a.close()
        b.close()


def contrast(per,work,base,alternative):
    counts=[len(rows) for rows in work.values()]
    def values(q,plan):
        return sum(per[plan][f"{q}/{r['t']}"][0] for r in work[q])
    savings=np.array([values(q,base)-values(q,alternative) for q in work],dtype=float)
    den=np.asarray(counts)
    samples=np.random.default_rng(541923).integers(len(work),size=(10000,len(work)))
    boot=100*savings[samples].sum(1)/den[samples].sum(1)
    return dict(warm_probes_saved=int(savings.sum()),saved_per_100_transactions=100*savings.sum()/den.sum(),
                bootstrap_ci95_per_100=np.percentile(boot,[2.5,97.5]).tolist(),
                streams_better=int((savings>0).sum()),streams_worse=int((savings<0).sum()),streams_equal=int((savings==0).sum()))


def main(args):
    reg=registration()
    if args.register:
        assert not (HERE/"results.json").exists()
        save("registration.json",reg)
        print("Protocol recorded")
        return
    assert reg==read(HERE/"registration.json")
    work=read(OLD/"workload.json.gz")
    refs,_=oracle(work)
    small=finite()
    per={};tables={};restarts={}
    with tempfile.TemporaryDirectory(dir=args.scratch) as d:
        d=Path(d)
        for name,l in PLANS:
            plan=f"{name}-{l}"
            per[plan],tables[plan]=replay(d/(plan+".sqlite"),name,l,work,refs)
            restarts[plan]=restart(d/(plan+"-restart.sqlite"),name,l,work,refs)
    expected=read(HERE.parent/"cutoff"/"correctness.json")["packets"]["boundary"]
    assert all(v["snapshot_hash"]==expected["packet_hash"] and v["snapshot_rows"]==expected["rows"] for v in tables.values())
    assert tables["boundary-8"]["warm_probes"]==expected["counts"]["index"]==39
    assert tables["boundary-8"]["cold_probes"]==expected["counts"]["cold_top_selects"]==40
    contrasts={"boundary-8 minus "+p:contrast(per,work,"boundary-8",p) for p in tables if p.startswith("lazy")}
    contrasts.update({f"eager-{l} minus lazy-{l}":contrast(per,work,f"eager-{l}",f"lazy-{l}") for l in (8,9,12,16)})
    result=dict(events=sum(map(len,work.values())),versions=sum(map(len,refs.values())),streams=len(work),k=list(KS),
                plans=tables,comparisons=contrasts,adversarial=small,restart_trace_events=restarts,sqlite=sqlite3.sqlite_version)
    if args.verify:
        assert result==read(HERE/"results.json")
        assert dict(columns=list(COLS),plans=per)==read(HERE/"event-costs.json.gz")
        print("Verified event costs, all packets and finite-state transitions.")
    else:
        save("event-costs.json.gz",dict(columns=list(COLS),plans=per))
        save("results.json",result)
        print([(p,tables[p]["warm_probes"],tables[p]["warm_rows"],tables[p]["mean_pairs"]) for p in tables])
        print(contrasts["boundary-8 minus lazy-12"])


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--register",action="store_true")
    ap.add_argument("--verify",action="store_true")
    ap.add_argument("--scratch", type=Path, default=HERE)
    main(ap.parse_args())

