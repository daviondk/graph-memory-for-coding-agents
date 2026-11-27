"""Frozen holdout evaluation on genuinely separate histories, using the same SQLite readers."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import random
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"reconcile"))
from bench_sketch import simulate,aggregate,BlockStore,load,save,prepare
sys.path.insert(0,str(HERE.parent/"references"))
from measure_refs import METHODS,HORIZONS,split_run,run_one,summarize
from audit import chosen
import shutil


def replay():
    streams=load(HERE/"events.json.gz")
    summaries={};physical={}
    rng=random.Random(59091)
    with TemporaryDirectory(dir=HERE) as folder:
        root=Path(folder)
        for repo,stream in streams.items():
            for p in ("long","B"):
                ops,_=prepare(stream,p)
                base=root/"prefix.sqlite"
                with closing(BlockStore(base,"filelist",True)) as store:
                    summaries[p+"/"+repo]=simulate(store,ops)
                base.unlink()
                history,rev,tail=split_run(ops,base)
                controls={"full":chosen(history,None,"recent")[0],
                          "demand1024":chosen(history,1024,"demand")[0]}
                arms=["cold",*(s+"/"+m for s in controls for m in METHODS)]
                rng.shuffle(arms)
                rows={}
                for name in arms:
                    branch=root/"branch.sqlite";shutil.copyfile(base,branch)
                    mode=name.split("/")[-1]
                    saved=controls[name.split("/")[0]] if mode!="cold" else set()
                    rows[name]=run_one(branch,history,rev,saved,mode,tail)
                    branch.unlink()
                base.unlink()
                physical[p+"/"+repo]=rows
    return dict(sketch=summaries,reference=physical)


def metrics(raw):
    x=aggregate(raw["sketch"])
    y={}
    for case,arms in raw["reference"].items():
        p=case.split("/")[0]
        assert len({a["ranking_sha"] for a in arms.values()})==1
        assert len(arms["cold"]["queries"])==len(raw["sketch"][case])
        for h in HORIZONS:
            tab=y.setdefault(p,{}).setdefault(str(h),{})
            for name,run in arms.items():
                tab.setdefault(name,Counter()).update(summarize(run,h))
            for select in ("demand1024","full"):
                a,b,c=(summarize(arms[select+"/"+m],h) for m in ("copy","eager","lazy"))
                assert a["charged"]-c["charged"]==2*(a["write"]-c["write"])-c["first_touch"]
                assert b["charged"]-c["charged"]==b["pre_body"]-c["first_touch"]
    return dict(sketch=x,reference=y)


if __name__=="__main__":
    ap=ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    file=HERE/"queries.json.gz"
    raw=load(file) if args.verify else replay()
    results=metrics(raw)
    if args.verify:assert results==load(HERE/"results.json")
    else:
        save(file,raw);save(HERE/"results.json",results)
    for p,t in results["sketch"]["groups"].items():
        print(p,t["1024/exact"]["queries"],{n:v["charged"] for n,v in t.items()})
