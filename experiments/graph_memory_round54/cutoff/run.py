"""Registered paired validation and timing against the index-based SQLite plan."""
import argparse
from collections import Counter
from hashlib import sha256
from itertools import product
import gzip
import hashlib
import json
from pathlib import Path
import platform
import random
import sqlite3
import tempfile
import time
import numpy as np
from cutoff_store import CutoffStore, PLANS, local_top
from core import KS, M, OLD, connect, read
from bench import oracle,schedule

HERE=Path(__file__).resolve().parent
def encode(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()+b"\n"
def save(name,value):
    raw=encode(value)
    (HERE/name).write_bytes(gzip.compress(raw,mtime=0) if name.endswith(".gz") else raw)
def sha(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def enumerate_small():
    stats=Counter()
    for oldvals in product(range(-1,3),repeat=4):
        for newvals in product(range(-1,3),repeat=4):
            if any(a>=0>b for a,b in zip(oldvals,newvals)):continue
            dirty={i:b for i,(a,b) in enumerate(zip(oldvals,newvals)) if a!=b}
            for k in (1,2,3):
                def order(seq):
                    return sorted([(i,v) for i,v in enumerate(seq) if v>=0],key=lambda t:(-t[1],t[0]))[:k]
                old,actual=order(oldvals),order(newvals)
                for plan in ("unchanged","boundary"):
                    pred,how=local_top(old,dirty,k,plan)
                    assert pred is None or pred==actual,(oldvals,newvals,k,plan)
                    stats[plan+"_"+how]+=1
    return stats

def cross_connection(folder,work,refs,mode):
    a=connect(folder/(mode+"-fault.sqlite"));b=connect(folder/(mode+"-fault.sqlite"))
    try:
        p=CutoffStore(a,mode);s=CutoffStore(b,mode,False);q="q11"
        for i,row in enumerate(work[q]):
            writer=(p,s)[i%2]
            if row["t"]==17:
                try:writer.update(q,row,fault=True)
                except RuntimeError:pass
                else:raise AssertionError("rollback missing")
                assert s.get(q,16,M)==refs[q][16]
                try:p.get(q,17,M)
                except ValueError:pass
                else:raise AssertionError("uncommitted data visible")
            assert writer.update(q,row) and not writer.update(q,row)
            for k in KS:assert (p,s)[(i+1)%2].get(q,row["t"],k)==refs[q][row["t"]][:k]
        try:p.update(q,work[q][-1]|{"sha":"invalid"})
        except ValueError:pass
        else:raise AssertionError("replay conflict missing")
    finally:a.close();b.close()

def replay(path,mode,work,refs,batch,verify):
    db=connect(path);clock=time.perf_counter_ns
    try:
        start=clock();store=CutoffStore(db,mode);init=clock()-start
        write=reads=0
        for q,events in work.items():
            for row in events:
                start=clock();ok=store.update(q,row);write+=clock()-start
                assert ok
                v=row["t"]
                if batch[q,v]:
                    start=clock();out=[store.get(q,t,k) for t,k in batch[q,v]];reads+=clock()-start
                    assert out==[refs[q][t][:k] for t,k in batch[q,v]]
        start=clock();assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]==0
        check=clock()-start
        result=dict(ns=init+write+reads+check,init=init,write=write,reads=reads,checkpoint=check,
                    counts=dict(store.stats),db_bytes=path.stat().st_size)
        if verify:
            for q,versions in refs.items():
                for t,expect in enumerate(versions):
                    for k in KS:assert store.get(q,t,k)==expect[:k] and store._history(q,t,k)==expect[:k]
            rows=[(q,j,t,x.hex()) for q,j,t,x in db.execute("SELECT q,part,rev,payload FROM packet ORDER BY q,part,rev")]
            result.update(rows=len(rows),packet_hash=sha256(encode(rows)).hexdigest())
        return result
    finally:db.close()

def summarize(runs):
    res={}
    boots=np.random.default_rng(540421).integers(0,7,(10000,7))
    for m in (0,8):
        item=res[str(m)]={}
        for col in ("ns","write","reads"):
            values={p:np.array([r[col] for r in sorted(runs,key=lambda r:r["rep"]) if r["mode"]==m and r["plan"]==p],dtype=float) for p in PLANS}
            item[col+"_ms"]={p:float(v.mean()/1e6) for p,v in values.items()}
            if not values["index"].any():continue
            for p in ("boundary","unchanged"):
                a,b=values["index"],values[p]
                item[col+"_index_over_"+p]=dict(ratio=float(a.mean()/b.mean()),ci=np.percentile(a[boots].mean(1)/b[boots].mean(1),[2.5,97.5]).tolist(),
                                               wins=int((a>b).sum()))
    return res
def main(scratch,verify):
    work=read(OLD/"workload.json.gz");refs,_=oracle(work);batches,_=schedule(work)
    reg={"protocol":sha(HERE/"PROTOCOL_RU.md"),"code":{n:sha(HERE/n) for n in ("run.py","cutoff_store.py")},
         "base":{n:sha(HERE.parent/"multi_read"/n) for n in ("core.py","bench.py")},
         "work":sha(OLD/"workload.json.gz"),"seed":540421,"reps":7,"k":list(KS),"python":platform.python_version(),"sqlite":sqlite3.sqlite_version}
    if verify:
        saved=read(HERE/"registration.json")
        assert all(reg[k]==v for k,v in saved.items() if k not in ("python","sqlite"))
    else:save("registration.json",reg)
    small=enumerate_small();ch={};runs=[];rng=random.Random(540421)
    scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        path=Path(tmp)
        for p in PLANS:
            ch[p]=replay(path/(p+".sqlite"),p,work,refs,batches[8],True)
            cross_connection(path,work,refs,p)
        assert len({r["packet_hash"] for r in ch.values()})==1
        audit=dict(small=dict(small),versions=sum(map(len,refs.values())),packets={p:{k:r[k] for k in ("counts","rows","packet_hash")} for p,r in ch.items()})
        if verify:
            assert audit==read(HERE/"correctness.json")
            assert summarize(read(HERE/"timings.json.gz"))==read(HERE/"results.json")
            print("Verified",audit["versions"],audit["packets"]["boundary"])
            return
        save("correctness.json",audit)
        for rep in range(7):
            cells=[(p,m) for m in (0,8) for p in PLANS];rng.shuffle(cells)
            for j,(p,m) in enumerate(cells):
                f=path/f"{rep}-{j}.sqlite";out=replay(f,p,work,refs,batches[m],False)
                runs.append(dict(rep=rep,position=j,plan=p,mode=m,**out));f.unlink()
    save("timings.json.gz",runs);save("results.json",summarize(runs));print(audit["packets"],summarize(runs)["8"])
if __name__=="__main__":
    cli=argparse.ArgumentParser();cli.add_argument("--scratch",type=Path,default=Path("D:/CodexResearch/x20-r54-cutoff"))
    cli.add_argument("--verify",action="store_true");a=cli.parse_args();main(a.scratch,a.verify)
