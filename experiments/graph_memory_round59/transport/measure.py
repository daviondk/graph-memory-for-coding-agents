"""Measure end-to-end, closed-loop queries against one actual SQLite endpoint per run."""
from collections import Counter
from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import platform
from random import Random
from shutil import copyfile
import socket
import sqlite3
import statistics
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from types import SimpleNamespace
from wire import service

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/"reconcile"))
from bench_sketch import BlockStore,Hot,SketchPolicy,XOR,prepare

KEYS=("posting_req_bytes","posting_resp_bytes","posting_calls","bodies_req_bytes","bodies_resp_bytes","bodies_calls")
MODES=((caps,m,wait) for caps in (1024,4096) for m in ("exact","xor") for wait in (0,2))


def get(path):
    b=path.read_bytes();return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)


def put(path,z):
    x=(json.dumps(z,ensure_ascii=True,sort_keys=True,separators=(",",":") if path.suffix==".gz" else None,
                  indent=2 if path.suffix!=".gz" else None)+"\n").encode()
    path.write_bytes(gzip.compress(x,mtime=0) if path.suffix==".gz" else x)


def h(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(path,ops,refs,cap,mode,lag):
    start=perf_counter_ns()
    with closing(BlockStore(path,"filelist")) as writer:
        cut=writer.next_id;hot=Hot()
        with service(path,lag) as (rpc,serverlog,timing):
            proxy=SimpleNamespace(db=rpc,next_id=cut)
            reader=SketchPolicy(proxy,hot,None if mode=="exact" else XOR,cap)
            opened=perf_counter_ns();work=[];idx=0;hasher=hashlib.sha256();payload=Counter()
            for op in ops:
                if op[0]=="w":
                    _,j,rev,files=op;assert writer.append(j,rev,files)
                    hot.append(j,files);proxy.next_id=writer.next_id;reader.after_write(j,files)
                else:
                    _,anchor,tie,prior,expect=op
                    prev=rpc.ledger.counts.copy()
                    t=perf_counter_ns()
                    ans,x=reader.read(anchor,tie,prior)
                    ns=perf_counter_ns()-t
                    assert ans==expect
                    observed=rpc.ledger.counts-prev
                    old=refs[idx];idx+=1
                    assert old["anchor"]==anchor and old["prefix"]==writer.next_id
                    target=old["arms"][f"{cap}/{mode}"]
                    for k in ("posting_bytes","body_bytes","posting_calls","body_calls"):
                        assert x[k]==target.get(k,0),(anchor,k,x[k],target.get(k,0))
                    assert observed["posting_calls"]==x["posting_calls"] and observed["bodies_calls"]==x["body_calls"]
                    work.append([writer.next_id,anchor,ns,x["posting_bytes"],x["body_bytes"],*[observed[k] for k in KEYS]])
                    hasher.update((json.dumps(ans,separators=(",",":"))+"\n").encode())
                    payload.update({"posting_sql":x["posting_bytes"],"bodies_sql":x["body_bytes"]})
            stopped=perf_counter_ns()
            assert idx==len(refs) and reader.cache.size<=cap
            client_end=rpc.ledger.seal()
        assert client_end==serverlog.seal()
    return dict(fence=cut,n=len(work),data=work,source_values=payload,read_wall_ns=sum(a[2] for a in work),
                setup_ns=opened-start,full_wall_ns=stopped-opened,ranking_sha=hasher.hexdigest(),
                request_sha=client_end["request_sha"],response_sha=client_end["response_sha"],wire=client_end["counts"],
                explicit_delay_ns=timing["actual_emulated_sleep_ns"])


def compute():
    hist=get(ROOT/"holdout/events.json.gz");old=get(ROOT/"holdout/queries.json.gz")["sketch"]
    data={}
    plans={}
    with TemporaryDirectory(dir=HERE) as td:
        td=Path(td)
        for repo,events in hist.items():
            ops,_=prepare(events,"B");n=sum(o[0]=="w" for o in ops);cut=n//2
            base=td/(hashlib.sha256(repo.encode()).hexdigest()[:12]+".sqlite")
            with closing(BlockStore(base,"filelist",True)) as db:
                at=0
                while db.next_id<cut:
                    op=ops[at];at+=1
                    if op[0]=="w":
                        _,j,rev,fs=op;assert db.append(j,rev,fs)
                assert db.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
            plans[repo]=(base,ops[at:],old["B/"+repo])
        rng=Random(590711);all_modes=list(MODES)
        for rep in range(3):
            for name in rng.sample(list(sorted(plans)),len(plans)):
                base,tail,refs=plans[name];variant=td/"serve.sqlite"
                for cap,mode,delay in rng.sample(all_modes,len(all_modes)):
                    key=f"{rep}/{name}/{cap}/{mode}/{delay}"
                    copyfile(base,variant)
                    try:data[key]=run(variant,tail,refs,cap,mode,delay)
                    finally:variant.unlink()
                print("block",rep+1,"project",name,"done",flush=True)
            put(HERE/"raw.json.gz",data)
    return data


def aggregate(data):
    raw={}
    for label,r in data.items():
        rep,project,repo,cap,mode,lag=label.split("/")
        g=f"{cap}/{mode}/{lag}";s=raw.setdefault(g,{}).setdefault(rep,Counter())
        d=Counter(r["wire"]);d.update(r["source_values"])
        d.update(dict(n=r["n"],query_ns=r["read_wall_ns"],full_ns=r["full_wall_ns"],setup_ns=r["setup_ns"],
                      emulated_actual_ns=r["explicit_delay_ns"]))
        s.update(d)
    result={}
    for g,reps in raw.items():
        entries=[reps[str(i)] for i in range(3)]
        for f in (*KEYS,"posting_sql","bodies_sql","n"):
            assert len({x[f] for x in entries})==1
        c=entries[0]
        result[g]=dict(queries=c["n"],round_trips=c["posting_calls"]+c["bodies_calls"],sql_bytes=c["posting_sql"]+c["bodies_sql"],
            request_bytes=c["posting_req_bytes"]+c["bodies_req_bytes"],reply_bytes=c["posting_resp_bytes"]+c["bodies_resp_bytes"],
            two_way=sum(c[k] for k in KEYS if k.endswith("bytes")),counters={k:c[k] for k in KEYS},
            times={f:dict(median=statistics.median(x[f] for x in entries),blocks=[x[f] for x in entries])
                   for f in ("query_ns","full_ns","setup_ns","emulated_actual_ns")})
    return result


def main():
    hooks=[HERE/"PROTOCOL_RU.md",HERE/"wire.py",HERE/"measure.py",ROOT/"holdout/events.json.gz",
           ROOT/"holdout/queries.json.gz",ROOT/"reconcile/summary_cache.py"]
    runtime=dict(python=sys.version,os=platform.platform(),sqlite=sqlite3.sqlite_version,driver="TCP_NODELAY on both sockets, IPv4 loopback",
                 clock="perf_counter_ns",columns=["prefix","anchor","query_ns","posting_sql_bytes","body_sql_bytes",*KEYS],
                 inputs={p.name:h(p) for p in hooks},random_seed=590711)
    if "--verify" in sys.argv:
        z=get(HERE/"raw.json.gz")
        assert aggregate(z)==get(HERE/"results.json")
        recorded=get(HERE/"run-seal.json")
        assert recorded["inputs"]==runtime["inputs"] and recorded["raw"]==h(HERE/"raw.json.gz")
    else:
        z=compute();put(HERE/"results.json",aggregate(z))
        put(HERE/"run-seal.json",dict(**runtime,raw=h(HERE/"raw.json.gz"),outputs=h(HERE/"results.json")))
    print("runs",len(z),"exact queries",sum(r["n"] for r in z.values()))


if __name__=="__main__":main()
