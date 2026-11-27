"""Matched holdout transfer timings, with a shared writer and warmed SQLite pages."""
from argparse import ArgumentParser
from collections import Counter
from itertools import combinations
from pathlib import Path
from random import Random
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from fast_postings import Fast,HERE,SketchPolicy,XOR,build,add,unpack_full,contains,varints,unpack
from bench_sketch import BlockStore,Hot,load,prepare,save

SEED=59123
ARMS=("compact","append","delta","xor_decode","xor_native")


def checks():
    rng=Random(SEED)
    tests=updates=0
    domain=[0,1,2,63,126,127,128,129,255,256,16383,16384,999999,1000001]
    for _ in range(270):
        vals=sorted(rng.sample(domain,rng.randrange(len(domain)+1)))
        raw=varints(vals)
        for n in (*domain,*range(44),*range(120,140)):
            assert contains(raw,varints((n,)))==(n in vals)
            tests+=1
        for k in range(len(vals)+1):
            for delta in (False,True):
                b=build(vals[:k],delta)
                for j in vals[k:]:
                    b=add(b,j)
                    updates+=1
                assert unpack_full(b)==tuple(vals)
    return dict(memberships=tests,appends=updates)


def case(path,ops,rng):
    store=BlockStore(path,"filelist",True)
    cut=sum(op[0]=="w" for op in ops)//2
    arms={}
    counters={}
    trace=[]
    for op in ops:
        if store.next_id==cut and not arms:
            store.close();store=BlockStore(path,"filelist")
            for table,col in (("posting","js"),("event","members")):
                sum(len(r[0]) for r in store.db.execute("SELECT "+col+" FROM "+table))
            hot=Hot()
            for limit in (1024,4096):
                for mode in ARMS:
                    name=f"{limit}/{mode}"
                    arms[name]=SketchPolicy(store,hot,None,limit) if mode=="compact" else Fast(store,hot,mode,limit)
                    counters[name]=Counter()
        if op[0]=="w":
            _,j,rev,ids=op
            assert store.append(j,rev,ids)
            if arms:
                hot.append(j,ids)
                for name in rng.sample(list(arms),len(arms)):
                    start=perf_counter_ns()
                    arms[name].after_write(j,ids)
                    counters[name]["update_ns"]+=perf_counter_ns()-start
        elif arms:
            one={}
            _,f,tie,prior,gold=op
            for name in rng.sample(list(arms),len(arms)):
                start=perf_counter_ns()
                ranked,stats=arms[name].read(f,tie,prior)
                elapsed=perf_counter_ns()-start
                assert ranked==gold
                counters[name]["read_ns"]+=elapsed
                counters[name]["bytes"]+=stats["posting_bytes"]+stats["body_bytes"]
                counters[name]["queries"]+=1
                one[name]=[stats["posting_bytes"],stats["body_bytes"],elapsed]
            for n in (1024,4096):
                assert one[f"{n}/xor_decode"][:2]==one[f"{n}/xor_native"][:2]
                assert arms[f"{n}/xor_decode"].cache.items==arms[f"{n}/xor_native"].cache.items
            trace.append(one)
    store.close()
    return dict(counters=counters,trace=trace)


def run():
    streams=load(HERE.parent/"holdout/events.json.gz")
    ops={repo:prepare(history,"B")[0] for repo,history in streams.items()}
    raw=[]
    rng=Random(SEED)
    with TemporaryDirectory(dir=HERE) as tmp:
        path=Path(tmp)/"history.sqlite"
        for rep in range(3):
            raw.append({})
            for repo in rng.sample(list(ops),len(ops)):
                raw[-1][repo]=case(path,ops[repo],rng);path.unlink()
    return raw


def aggregate(raw):
    out={}
    for cap in (1024,4096):
        for mode in ARMS:
            k=f"{cap}/{mode}"
            values=[sum((Counter(r["counters"][k]) for r in rep.values()),Counter()) for rep in raw]
            assert len({v["bytes"] for v in values})==1
            cols={metric:[v[metric] for v in values] for metric in ("bytes","read_ns","update_ns","queries")}
            cols["combined_ns"]=[v["read_ns"]+v["update_ns"] for v in values]
            out[k]=cols
    return dict(measures=out,encoding=checks())


if __name__=="__main__":
    ap=ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    path=HERE/"runs.json.gz"
    raw=load(path) if args.verify else run()
    result=aggregate(raw)
    if args.verify:assert result==load(HERE/"results.json")
    else:save(path,raw);save(HERE/"results.json",result)
    for k,v in result["measures"].items():
        print(k,v["bytes"][0],*[round(median(v[m])/1e6,2) for m in ("read_ns","update_ns","combined_ns")])
