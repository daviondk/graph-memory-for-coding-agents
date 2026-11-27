"""Run paired, randomized reader calls on the same SQLite source at every prefix."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from summary_cache import SketchPolicy, Policy, NUM, XOR, MOMENTS
from lazy_reader import BlockStore, Hot
from run_lazy import cases, prepare, save, load

HERE=Path(__file__).resolve().parent
LIMITS=(1024,4096)
MODES={"exact":None,"count":NUM,"xor":XOR,"moments":MOMENTS}


def simulate(store,ops,make_arms=None):
    n=sum(op[0]=="w" for op in ops)
    cut=n//2
    arms={}
    out=[]
    rng=Random(59051)
    for op in ops:
        if store.next_id==cut and not arms:
            hot=Hot()
            arms={(cap,kind):SketchPolicy(store,hot,t,cap) for cap in LIMITS for kind,t in MODES.items()}
            for cap in LIMITS:
                for kind in ("joint","events"):
                    arms[cap,kind]=Policy(store,hot,kind,cap)
            if make_arms is not None:arms=make_arms(store,hot)
        if op[0]=="w":
            _,j,rev,files=op
            assert store.append(j,rev,files)
            if arms:
                hot.append(j,files)
                for h in arms.values():h.after_write(j,files)
        elif arms:
            _,f,tie,prior,expected=op
            record=dict(anchor=f,prefix=store.next_id,arms={})
            for key in rng.sample(list(arms),len(arms)):
                h=arms[key]
                start=perf_counter_ns()
                ans,stats=h.read(f,tie,prior)
                ns=perf_counter_ns()-start
                assert ans==expected and h.cache.size<=key[0]
                if isinstance(stats,list):
                    rows=dict(posting_bytes=stats[2],body_bytes=stats[3],posting_calls=stats[0],body_calls=stats[1])
                else:rows=dict(stats)
                rows.update(read_ns=ns,resident=h.cache.size)
                record["arms"][f"{key[0]}/{key[1]}"]=rows
            out.append(record)
    for h in arms.values():h.cache.inventory()
    return out


def compute():
    raw={}
    with TemporaryDirectory(dir=HERE) as t:
        for group,repo,p,rows in cases():
            ops,_=prepare(rows,p)
            db=Path(t)/"events.sqlite"
            with closing(BlockStore(db,"filelist",True)) as store:
                raw[group+"/"+repo]=simulate(store,ops)
            db.unlink()
    return raw


def aggregate(raw):
    groups={}; projects={}
    for key,rows in raw.items():
        group=key.split("/",1)[0]
        counts=groups.setdefault(group,{})
        one={}
        for name in (f"{l}/{m}" for l in LIMITS for m in (*MODES,"joint","events")):
            data=Counter()
            for row in rows:
                data.update({k:v for k,v in row["arms"][name].items() if k!="resident"})
            data["charged"]=data["posting_bytes"]+data["body_bytes"]
            data["queries"]=len(rows)
            counts.setdefault(name,Counter()).update(data)
            one[name]=data["charged"]
        projects[key]=one
    return {"groups":groups,"projects":projects}


if __name__=="__main__":
    p=ArgumentParser()
    p.add_argument("--verify",action="store_true")
    args=p.parse_args()
    rawpath=HERE/"runs.json.gz"
    raw=load(rawpath) if args.verify else compute()
    result=aggregate(raw)
    baseline=load(HERE.parent/"lazy/runs.json.gz")["cases"]
    for group,values in result["groups"].items():
        for method in ("events","joint"):
            for cap in LIMITS:
                key=f"{cap}/{method}"
                assert values[key]["charged"]==sum(
                    sum(r[2:4]) for name,v in baseline.items()
                    if name.startswith(group+"/") for r in v["reads"][f"B8-{method}-{cap}"])
    if args.verify:assert result==load(HERE/"results.json")
    else:
        save(rawpath,raw);save(HERE/"results.json",result)
    for g,values in result["groups"].items():
        print(g,{m:v["charged"] for m,v in values.items()})
