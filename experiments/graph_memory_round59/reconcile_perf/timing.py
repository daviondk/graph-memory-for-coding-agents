"""Paired warm-SQLite timing of the existing full and XOR graph readers."""
import argparse
from collections import Counter
import ctypes
import hashlib
from pathlib import Path
import platform
import random
import sqlite3
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns, thread_time_ns

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/"reconcile"
sys.path.insert(0,str(SOURCE))
from bench_sketch import SketchPolicy, BlockStore, Hot, XOR, load, save
from run_lazy import prepare, source, GROUPS

SEED=59371
BLOCKS=5
ARMS={"1024/exact":(1024,None),"1024/xor":(1024,XOR),"4096/exact":(4096,None),"4096/xor":(4096,XOR)}
FIELDS=("read_ns","read_cpu","update_ns","update_cpu","sql_bytes","sql_calls","scan_bytes",
        "scan_objects","queries","writes","source_write_ns","common_hot_ns")


class ThreadClock:
    def __init__(self):
        if sys.platform!="win32":
            self.unit="thread_cpu_ns";self.read=thread_time_ns;return
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        get=kernel.GetCurrentThread;get.argtypes=[];get.restype=ctypes.c_void_p
        read=kernel.QueryThreadCycleTime
        read.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint64)]
        read.restype=ctypes.c_bool
        self.handle=get();self.count=ctypes.c_uint64()
        self.ptr=ctypes.byref(self.count)
        self.win_read=read;self.unit="thread_cycles";self.read=self.win_clock

    def win_clock(self):
        if not self.win_read(self.handle,self.ptr):
            raise ctypes.WinError(ctypes.get_last_error())
        return self.count.value


def run_case(path,ops,ref,clock,rng):
    cut=sum(op[0]=="w" for op in ops)//2
    store=BlockStore(path,"filelist",True)
    arms=None
    reads=[];writes=[]
    for op in ops:
        if arms is None and store.next_id==cut:
            store.close()
            store=BlockStore(path,"filelist")
            assert store.db.execute("PRAGMA synchronous").fetchone()==(2,)
            # Read the actual bytes now; no query-selected warmup or per-arm differences.
            warmed=sum(len(b) for table,column in (("event","members"),("posting","js"))
                       for b, in store.db.execute("SELECT "+column+" FROM "+table))
            hot=Hot()
            arms={name:SketchPolicy(store,hot,kind,cap) for name,(cap,kind) in ARMS.items()}
        if op[0]=="w":
            _,j,sha,files=op
            t=perf_counter_ns();accepted=store.append(j,sha,files);db_ns=perf_counter_ns()-t
            assert accepted
            if arms is None:continue
            t=perf_counter_ns();hot.append(j,files);hot_ns=perf_counter_ns()-t
            order=rng.sample(list(ARMS),len(ARMS))
            timing={}
            for name in order:
                c=clock.read();t=perf_counter_ns()
                arms[name].after_write(j,files)
                ns=perf_counter_ns()-t;cpu=clock.read()-c
                timing[name]=(ns,cpu)
            writes.append([j,db_ns,hot_ns,order,timing])
        elif arms is not None:
            _,anchor,tie,prior,expected=op
            original=ref[len(reads)]
            assert (store.next_id,anchor)==(original["prefix"],original["anchor"])
            order=rng.sample(list(ARMS),len(ARMS))
            record={}
            for name in order:
                c=clock.read();t=perf_counter_ns()
                rank,stats=arms[name].read(anchor,tie,prior)
                ns=perf_counter_ns()-t;cpu=clock.read()-c
                assert rank==expected
                baseline=original["arms"][name]
                assert stats==Counter({k:v for k,v in baseline.items() if k not in ("read_ns","resident")})
                assert arms[name].cache.size==baseline["resident"]
                record[name]=[ns,cpu,stats["posting_bytes"]+stats["body_bytes"],
                              stats["posting_calls"]+stats["body_calls"],stats["scan_bytes"],stats["scan_objects"]]
            reads.append([store.next_id,anchor,order,record])
    assert len(reads)==len(ref)
    for a in arms.values():a.cache.inventory()
    store.close()
    return dict(warmed_bytes=warmed,reads=reads,writes=writes)


def summarize(raw):
    result={}
    for block in range(BLOCKS):
        for key,c in raw["blocks"][str(block)].items():
            for name in ARMS:
                out=result.setdefault(name,{}).setdefault(str(block),Counter())
                for _,_,_,parts in c["reads"]:
                    ns,cpu,b,calls,scan,objects=parts[name]
                    out.update(read_ns=ns,read_cpu=cpu,sql_bytes=b,sql_calls=calls,scan_bytes=scan,
                               scan_objects=objects,queries=1)
                for _,db_ns,hot_ns,_,parts in c["writes"]:
                    ns,cpu=parts[name]
                    out.update(update_ns=ns,update_cpu=cpu,writes=1,source_write_ns=db_ns,common_hot_ns=hot_ns)
    for mode in ARMS:
        for k in ("sql_bytes","sql_calls","scan_bytes","scan_objects","queries","writes"):
            assert len({d[k] for d in result[mode].values()})==1
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--verify",action="store_true")
    verify=parser.parse_args().verify
    path=HERE/"timing-runs.json.gz";dest=HERE/"timing-results.json"
    seal=hashlib.sha256((HERE/"PROTOCOL_RU.md").read_bytes().replace(b"\r\n",b"\n")).hexdigest()
    ref=load(SOURCE/"runs.json.gz")
    if verify:
        raw=load(path)
        assert raw["protocol"]==seal and len(raw["blocks"])==BLOCKS
        assert all(len(b)==12 for b in raw["blocks"].values())
        for b in raw["blocks"].values():
            for k,v in b.items():
                assert len(v["reads"])==len(ref[k])
                for rec,base in zip(v["reads"],ref[k]):
                    assert rec[:2]==[base["prefix"],base["anchor"]]
                    for m,z in rec[3].items():
                        o=Counter(base["arms"][m]);assert z[2:]==[o["posting_bytes"]+o["body_bytes"],
                              o["posting_calls"]+o["body_calls"],o["scan_bytes"],o["scan_objects"]]
        assert summarize(raw)==load(dest)
        print("Verified five complete blocks and all per-query BLOB/call/scan counters.");return
    clock=ThreadClock()
    raw=load(path) if path.exists() else dict(protocol=seal,seed=SEED,blocks={},
             cpu_unit=clock.unit,sqlite=sqlite3.sqlite_version,python=sys.version,platform=platform.platform())
    assert raw["protocol"]==seal
    shell=[]
    for _ in range(1024):
        start=clock.read();t=perf_counter_ns();ns=perf_counter_ns()-t;cc=clock.read()-start
        shell.append([ns,cc])
    if "empty_shell" not in raw:raw["empty_shell"]=shell
    inputs={g+"-B/"+k:v for g in GROUPS for k,v in source(g)[0].items()}
    with TemporaryDirectory(dir=HERE,prefix="clocked-") as folder:
        for block in range(BLOCKS):
            rows=raw["blocks"].setdefault(str(block),{})
            group_rng=random.Random(SEED+block)
            for key in group_rng.sample(sorted(inputs),len(inputs)):
                if key in rows:continue
                ops,_=prepare(inputs[key],"B")
                path_db=Path(folder)/"warm.sqlite"
                rows[key]=run_case(path_db,ops,ref[key],clock,random.Random(f"{SEED}/{block}/{key}"))
                path_db.unlink()
                assert not list(Path(folder).iterdir())
            save(path,raw)
            print("Block",block+1,"of",BLOCKS,flush=True)
    save(dest,summarize(raw))


if __name__=="__main__":
    main()
