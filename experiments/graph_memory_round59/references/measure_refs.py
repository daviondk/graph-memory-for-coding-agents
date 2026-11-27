"""Recover the same selected source events using three representations on real SQLite."""
import argparse
from collections import Counter
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import random
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from packet import R58, encode, decode, varints
from ref_reader import ReferenceReader
from checkpoint import persist
from block_store import BlockStore
from bench import panels,prepare,load,save
from audit import chosen
from experiment import footprint

HERE=Path(__file__).resolve().parent
SEED=59037
METHODS=("copy","compressed","eager","lazy")
HORIZONS=(0,1,4,16,"full")


def inputs():
    prior=panels()
    for p in ("long","B"):
        for repo,stream in sorted(prior[p].items()):
            yield "original",p,repo,stream
    for group in ("replication","seed_pair"):
        for repo,stream in sorted(load(R58.parent/"graph_memory_round57"/group/"events.json.gz").items()):
            for p in ("long","B"):
                yield group,p,repo,stream


def split_run(ops, prefix):
    writes=[o for o in ops if o[0]=="w"]
    fence=len(writes)//2
    with closing(BlockStore(prefix,"filelist",True)) as db:
        for _,j,revision,ids in writes[:fence]:
            assert db.append(j,revision,ids)
        assert db.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
    cut=next(i for i,op in enumerate(ops) if op[0]=="w" and op[1]==fence-1)+1
    history=[op[3] for op in writes[:fence]]
    return history,writes[fence-1][2],ops[cut:]


def run_one(path, history, revision, selected, mode, ops):
    members={j:history[j] for j in sorted(selected)}
    baseline_disk=path.stat().st_size
    encoded=b""
    if mode!="cold":
        encoded=encode(members,len(history),revision,mode)
        decoded,bodies=decode(encoded,len(history),bytes.fromhex(revision))
        assert decoded==selected
        if mode in ("copy","compressed"):
            assert bodies==members
        with closing(BlockStore(path,"filelist")) as writer:
            persist(writer.db,encoded)
            wal_bytes=Path(str(path)+"-wal").stat().st_size
            writer.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    else:wal_bytes=0
    snap_disk=path.stat().st_size
    begin=perf_counter_ns()
    h=ReferenceReader(path,mode)
    open_ns=perf_counter_ns()-begin
    assert not h.rejected and h.selected==selected and h.loaded_bytes==len(encoded)
    setup=dict(write=len(encoded),load=h.loaded_bytes,receipt=h.receipt_bytes,
               source=h.source_bytes,source_calls=h.source_calls,catalog_calls=h.open_calls,
               disk_before=baseline_disk,disk_checkpoint=snap_disk,wal=wal_bytes,
               codec=encoded[3] if encoded else None,selected=len(selected),
               selected_bodies=sum(len(varints(ids)) for ids in members.values()))
    def ram():
        return footprint((h.selected,h.pinned,h.pinned_for,h.complete,h.hot))
    pre_ram=ram()
    ns=[]
    records=[]
    digest=sha256()
    for op in ops:
        if op[0]=="w":
            _,j,rev,ids=op
            assert h.append(j,rev,ids)
        else:
            _,f,tie,prior,expected=op
            start=perf_counter_ns()
            answer,work=h.read(f,tie,prior)
            ns.append(perf_counter_ns()-start)
            assert answer==expected
            digest.update(json.dumps(answer,separators=(",",":")).encode()+b"\n")
            records.append([f,*work])
    assert h.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
    result=dict(setup=setup,queries=records,ranking_sha=digest.hexdigest(),
                time=dict(open_ns=open_ns,read_ns=sum(ns)),final_resident=len(h.pinned),
                start_sample_python=pre_ram,end_sample_python=ram(),disk_final=path.stat().st_size)
    h.close()
    return result


def summarize(row, count):
    s=row["setup"]
    q=row["queries"] if count=="full" else row["queries"][:count]
    out=Counter(write=s["write"],load=s["load"],receipt=s["receipt"],pre_body=s["source"],
                post_ptr=sum(r[2] for r in q),post_body=sum(r[4] for r in q))
    out["charged"]=sum(out.values())
    out.update(sql=s["source_calls"]+s["catalog_calls"]+sum(r[1]+r[3] for r in q),
               first_touch=sum(r[5] for r in q),queries=len(q))
    return dict(out)


def check(raw):
    totals={}
    natural=load(R58/"restart_transfer/no-padding.json")["projects"]
    compared=0
    for key,arms in raw["cases"].items():
        origin,panel,repo=key.split("/",2)
        prior=natural[origin+"-"+panel][repo]
        assert len({a["ranking_sha"] for a in arms.values()})==1
        for name,item in arms.items():
            for h in HORIZONS:
                group=totals.setdefault(origin+"/"+panel,{}).setdefault(str(h),{})
                group.setdefault(name,Counter()).update(summarize(item,h))
        for selection in ("demand1024","full"):
            copy,compressed,eager,lazy=(arms[selection+"/"+t] for t in METHODS)
            assert summarize(copy,"full")["charged"]==prior[selection]["charged"]
            assert summarize(arms["cold"],"full")["charged"]==prior["cold"]["charged"]
            assert eager["setup"]["write"]==lazy["setup"]["write"]
            assert copy["setup"]["selected_bodies"]==eager["setup"]["source"]
            assert [q[:5] for q in copy["queries"]]==[q[:5] for q in compressed["queries"]]
            for a,b,c in zip(copy["queries"],eager["queries"],lazy["queries"]):
                assert a[0:3]==b[0:3]==c[0:3] and a[4]==b[4]==c[4]-c[5]
                compared+=1
            for h in HORIZONS:
                a,b,c=(summarize(i,h) for i in (copy,eager,lazy))
                assert c["first_touch"]<=eager["setup"]["source"]
                assert a["charged"]-c["charged"]==2*(a["write"]-c["write"])-c["first_touch"]
                assert b["charged"]-c["charged"]==eager["setup"]["source"]-c["first_touch"]
    return dict(groups=totals,compared_query_triplets=compared)


def perform():
    raw=dict(seed=SEED,sqlite=sqlite3.sqlite_version,cases={})
    rng=random.Random(SEED)
    with TemporaryDirectory(dir=HERE) as temp:
        root=Path(temp)
        for group,p,repo,stream in inputs():
            ops,_=prepare(stream,p)
            prefix=root/"prefix.sqlite"
            history,rev,rest=split_run(ops,prefix)
            keep={name:chosen(history,cap,policy)[0] for name,cap,policy in
                  (("demand1024",1024,"demand"),("full",None,"recent"))}
            variants=["cold",*(v+"/"+m for v in keep for m in METHODS)]
            rng.shuffle(variants)
            arms={}
            for name in variants:
                path=root/"branch.sqlite"
                shutil.copyfile(prefix,path)
                mode=name.split("/")[-1]
                selected=set() if mode=="cold" else keep[name.split("/")[0]]
                arms[name]=run_one(path,history,rev,selected,mode,rest)
                path.unlink()
            raw["cases"]["/".join((group,p,repo))]=arms
            prefix.unlink()
        assert not list(root.iterdir())
    return raw


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    rawpath=HERE/"runs.json.gz"
    raw=load(rawpath) if args.verify else perform()
    results=check(raw)
    if args.verify:
        assert len(raw["cases"])==33 and results==load(HERE/"results.json")
    else:
        save(rawpath,raw)
        save(HERE/"results.json",results)
    print("Post-restart paired query triplets:",results["compared_query_triplets"])
    for g,v in results["groups"].items():
        print(g,{k:r["charged"] for k,r in v["full"].items()})
