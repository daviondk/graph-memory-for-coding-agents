"""Matched continuous and cold-cache replays of the same durable graph archive."""
import argparse
from collections import Counter,deque
import gzip
import hashlib
import json
import platform
from pathlib import Path
import random
import sqlite3
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from reader import Hot, MODES as FILE_MODES, Reader
from bench import load,save,prepare,panels
from store import Store
from block_store import R56

HERE=Path(__file__).resolve().parent
MODES=(*FILE_MODES,"r56_split")
SEED=57118
REPS=5
FIELDS=("posting_calls","posting_blobs","posting_bytes","body_calls","body_blobs","body_bytes","hot_events","hits")


def footprint(root):
    seen=set()
    def walk(x):
        ident=id(x)
        if ident in seen:return 0
        seen.add(ident)
        n=sys.getsizeof(x)
        if isinstance(x,dict):
            return n+sum(walk(k)+walk(v) for k,v in x.items())
        if isinstance(x,(tuple,list,set,deque)):
            return n+sum(map(walk,x))
        if hasattr(x,"__dict__"):
            return n+walk(vars(x))
        return n
    return walk(root)


def inventory(handle,mode):
    if mode=="r56_split":
        state=(handle.owned,handle.owners,handle.live,handle.incident,handle.cold)
        return dict(bytes_py=footprint(state),bodies=len(handle.live),refs=sum(handle.owners.values()),
                    incidents=sum(map(len,handle.incident.values())),cold=len(handle.cold))
    if handle.hot is not None:
        h=handle.hot
        return dict(bytes_py=footprint((h,handle.known_new)),bodies=len(h.live),refs=h.refs,incidents=h.members,
                    lost_shared=len(h.lost_shared),lost_own=len(h.lost_own),known_new=len(handle.known_new),
                    logical_budget=h.budget())
    if handle.lru is not None:
        l=handle.lru
        return dict(bytes_py=footprint(l),anchors=len(l.maps),pairs=sum(map(len,l.maps.values())),
                    logical_charge=l.charge,logical_budget=l.budget)
    return dict(bytes_py=0)


def open_handle(path,mode,create=False):
    return Store(path,"split",create) if mode=="r56_split" else Reader(path,mode,create)


def budget(ops,mid):
    events=[op for op in ops if op[0]=="w"]
    h=Hot();out=[]
    for _,j,sha,ids in events:
        if mid and j==len(events)//2:h=Hot()
        h.append(j,ids);out.append(h.budget())
    return out


def run(ops,budgets,path,mode,mid):
    start=perf_counter_ns();h=open_handle(path,mode,True);init_ns=perf_counter_ns()-start
    assert h.db.execute("PRAGMA synchronous").fetchone()==(2,)
    n=len(budgets);split=n//2
    after=False;qn=0;writes=0
    durable_ns=cache_ns=restart_ns=0
    restore_rows=restore_bytes=0
    decisions=[];states={}
    select={1,n//4,split-1,split,split+1,n*3//4,n}
    for op in ops:
        if not after and writes==split:
            if mid:
                h.close()
                start=perf_counter_ns();h=open_handle(path,mode);restart_ns=perf_counter_ns()-start
                if mode=="r56_split":
                    restore_rows=h.restore_rows;restore_bytes=h.restore_payload
                states["restart"]=inventory(h,mode)
            after=True
        if op[0]=="q":
            _,anchor,tie,prior,expected=op
            start=perf_counter_ns()
            ranking,work=h.read(anchor,tie,prior)
            ns=perf_counter_ns()-start
            assert ranking==expected,(mode,writes,anchor,ranking,expected)
            if mode=="r56_split":
                calls,rows,body_bytes=work
                work=(0,0,0,calls,rows,body_bytes,len(h.incident.get(anchor,())),0)
            phase=0 if not after else 1 if qn<10 else 2
            decisions.append((phase,ns,*work))
            if after:qn+=1
        else:
            _,j,rev,ids=op
            start=perf_counter_ns()
            if mode=="r56_split":
                ok=h.append(j,rev,ids)
                durable_ns+=perf_counter_ns()-start
            else:
                ok=h.store.append(j,rev,ids)
                fence=perf_counter_ns();durable_ns+=fence-start
                h.remember(j,ids,budgets[j]);cache_ns+=perf_counter_ns()-fence
            assert ok
            writes+=1
            if writes in select:states[str(writes)]=inventory(h,mode)
    assert h.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
    h.close()
    db=path.read_bytes()
    return dict(init_ns=init_ns,write_ns=durable_ns,cache_ns=cache_ns,restart_ns=restart_ns,
                restore_rows=restore_rows,restore_bytes=restore_bytes,events=writes,
                footprint=len(db),digest=hashlib.sha256(db).hexdigest(),queries=decisions,states=states)


def aggregate(raw,modes=MODES):
    collection={}
    for panel in ("B","long"):
        for mid in (False,True):
            for mode in modes:
                groups=[]
                for rep in range(REPS):
                    rows=[r for r in raw["runs"] if (r["panel"],r["restart"],r["mode"],r["rep"])==(panel,mid,mode,rep)]
                    if not rows:continue
                    assert len(rows)==(3 if panel=="long" else 6)
                    details=[q for r in rows for q in r["queries"]]
                    measures=dict(queries=len(details),footprint=sum(r["footprint"] for r in rows),
                                  restore_rows=sum(r["restore_rows"] for r in rows),restore_bytes=sum(r["restore_bytes"] for r in rows),
                                  sum_project_sampled_peak_python_bytes=sum(max(st["bytes_py"] for st in r["states"].values()) for r in rows),
                                  sum_project_final_python_bytes=sum(r["states"][str(r["events"])]["bytes_py"] for r in rows))
                    for phase in range(4):
                        group=details if phase==3 else [q for q in details if q[0]==phase]
                        prefix=("before","first10","later","all")[phase]
                        measures[prefix+"_n"]=len(group)
                        measures[prefix+"_read_ns"]=sum(q[1] for q in group)
                        for i,f in enumerate(FIELDS):measures[prefix+"_"+f]=sum(q[2+i] for q in group)
                    for name in ("init_ns","write_ns","cache_ns","restart_ns"):measures[name]=sum(r[name] for r in rows)
                    measures["mixed_ns"]=measures["write_ns"]+measures["cache_ns"]+measures["all_read_ns"]
                    groups.append(measures)
                if not groups:continue
                out={}
                for k,v in groups[0].items():
                    vs=[g[k] for g in groups]
                    if k.endswith("_ns") or k.endswith("_python_bytes"):
                        out[k]=[int(median(vs)),vs]
                    else:
                        assert all(x==v for x in vs),(k,vs)
                        out[k]=v
                collection[panel+("-restart-" if mid else "-continuous-")+mode]=out
    return collection


def check_digests(raw):
    signatures={}
    for r in raw["runs"]:
        if r["mode"]=="r56_split":continue
        key=r["panel"],r["repo"],r["restart"]
        assert signatures.setdefault(key,(r["footprint"],r["digest"]))==(r["footprint"],r["digest"]),key
    return len(signatures)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    path=HERE/"runs.json.gz"; out=HERE/"results.json"
    pins=load(R56/"durable/runs.json.gz")["oracle"]
    sig=hashlib.sha256((HERE/"PROTOCOL_RU.md").read_bytes().replace(b"\r\n",b"\n")).hexdigest()
    if args.verify:
        raw=load(path)
        assert len(raw["runs"])==REPS*9*2*len(MODES) and raw["oracle"]==pins and raw["protocol"]==sig
        assert check_digests(raw)==18 and aggregate(raw)==load(out)
        print("Verified 450 matched runs and 18 physical file digest groups.");return
    data=panels();inputs={}
    for panel in ("B","long"):
        for repo,stream in data[panel].items():
            ops,key=prepare(stream,panel)
            assert pins[panel+"/"+repo]==key
            inputs[panel,repo]=ops,(budget(ops,False),budget(ops,True))
    raw=load(path) if path.exists() else dict(seed=SEED,sqlite=sqlite3.sqlite_version,python=sys.version,platform=platform.platform(),
                                             oracle=pins,protocol=sig,runs=[])
    assert raw["protocol"]==sig and raw["oracle"]==pins
    done={(r["panel"],r["repo"],r["restart"],r["mode"],r["rep"]) for r in raw["runs"]}
    rng=random.Random(SEED)
    with TemporaryDirectory(dir=HERE,prefix="wal-") as td:
        for rep in range(REPS):
            for (panel,repo),(ops,budgets) in inputs.items():
                jobs=[(mid,mode) for mid in (False,True) for mode in MODES]
                for pos,(mid,mode) in enumerate(rng.sample(jobs,len(jobs))):
                    if (panel,repo,mid,mode,rep) in done:continue
                    path_db=Path(td)/"cache.sqlite"
                    row=run(ops,budgets[mid],path_db,mode,mid)
                    row.update(panel=panel,repo=repo,mode=mode,restart=mid,rep=rep,position=pos)
                    raw["runs"].append(row);path_db.unlink()
            check_digests(raw)
            save(path,raw);save(out,aggregate(raw))
            print("Completed paired block",rep+1,"of",REPS,flush=True)


if __name__=="__main__":
    main()
