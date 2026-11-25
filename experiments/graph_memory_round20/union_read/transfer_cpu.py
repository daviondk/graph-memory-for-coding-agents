"""Adapt a separately sealed upstream rank list to the immutable packing algorithm."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import argparse
import os
import time

import pack
import overlap_control
from pack import ROOT,RUNTIME,CACHE,OFF,load,sha,put

PRIV=RUNTIME/"x20-r20-union-adapted-ranks"


def pairs(x):
    if isinstance(x,dict):
        for k,v in x.items():
            if isinstance(v,str):yield k,v
            else:yield from pairs(v)
    elif isinstance(x,list):
        for v in x:yield from pairs(v)


def derived(tag,i):return PRIV/tag/f"ranks-{i}.json.gz"


def source_lock(tag,rank_dir,pattern,seal):
    assert tag in {"hash64","availability"} and seal.is_file()
    archived=sorted(rank_dir.glob(pattern));assert archived
    plan=load(ROOT/"design-lock.json");assert sha(ROOT/"pack.py")==plan["code"] and sha(ROOT/"PROTOCOL_RU.md")==plan["protocol"]
    refs=dict(pairs(load(seal)));actual={f.name:sha(f) for f in archived}
    assert all(refs.get(name)==digest for name,digest in actual.items()),"upstream seal has no matching filename or SHA"
    shard_by={p.name.split("-",1)[1][:-len(".json.gz")]:int(p.name.split("-",1)[0]) for p in CACHE.glob("*.json.gz")}
    cohort={r["query_id"]:r["trajectory_id"] for r in load(OFF/"cohort.json")};assert len(cohort)==2000
    items=defaultdict(list);seen=set()
    for f in archived:
        for r in load(f):
            q,t=r["q"],r["t"];assert q not in seen and cohort[q]==t
            seen.add(q);assert "rr" in r
            # Some native dev exporters omit the arms. Reconstitute only native whole-PU skip
            # with its original algorithm; pre-exported arms are checked again inside pack().
            if "arms" not in r:
                sel=[];used=0
                for n in r["rr"]:
                    if used+n["token_count"]<=2048:used+=n["token_count"];sel.append(n["node_id"])
                r={**r,"arms":{"skip":sel}}
            items[shard_by[t]].append(r)
    assert seen==cohort.keys() and set(items)==set(range(8))
    (PRIV/tag).mkdir(exist_ok=True,parents=True)
    dig={}
    for i,rows in items.items():
        p=derived(tag,i);put(p,sorted(rows,key=lambda x:(x["t"],x["q"])));dig[p.name]=sha(p)
    dest=dict(design=sha(ROOT/"design-lock.json"),protocol_addendum=sha(ROOT/"CPU_TRANSFER_RU.md"),code=sha(ROOT/"transfer_cpu.py"),
        ranks=dig,upstream={seal.name:sha(seal)},original_files=actual,tag=tag)
    put(ROOT/f"{tag}-plan.json",dest)
    put(ROOT/f"{tag}-duplicate-plan.json",dict(main=sha(ROOT/f"{tag}-plan.json"),
        protocol=sha(ROOT/"OVERLAP_CONTROL_RU.md"),code=sha(ROOT/"overlap_control.py"),pack=sha(ROOT/"pack.py")))


def worker(args):
    tag,i,variant=args
    pack.rankpath=derived;overlap_control.rankpath=derived
    return (pack.shard if variant=="main" else overlap_control.shard)((tag,i))


def forecast(tag,variant):
    src=load(ROOT/f"{tag}-plan.json");assert src["code"]==sha(ROOT/"transfer_cpu.py")
    assert load(ROOT/"design-lock.json")["code"]==sha(ROOT/"pack.py")
    ctl=load(ROOT/f"{tag}-duplicate-plan.json");assert ctl["code"]==sha(ROOT/"overlap_control.py")
    st=time.perf_counter()
    with ProcessPoolExecutor(max_workers=3) as pool:
        summary=list(pool.map(worker,[(tag,i,variant) for i in range(8)]))
    assert sum(x["n"] for x in summary)==2000
    if variant=="main":
        seal=dict(ranks=src["ranks"],plan=sha(ROOT/f"{tag}-plan.json"),shards=summary,wall_seconds=time.perf_counter()-st,
              cpu_worker_seconds=sum(r["cpu"] for r in summary));name=f"{tag}-forecast-seal.json"
    else:
        seal=dict(plan=sha(ROOT/f"{tag}-duplicate-plan.json"),shards=summary,wall=time.perf_counter()-st,cpu=sum(r["cpu"] for r in summary))
        name=f"{tag}-duplicate-seal.json"
    put(ROOT/name,seal)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("tag");p.add_argument("action",choices=["inputs","main","duplicate"])
    p.add_argument("--dir",type=Path);p.add_argument("--pattern");p.add_argument("--seal",type=Path)
    a=p.parse_args()
    if a.action=="inputs":source_lock(a.tag,a.dir,a.pattern,a.seal)
    else:forecast(a.tag,a.action)
