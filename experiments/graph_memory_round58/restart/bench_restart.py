"""Durable checkpoint-cost experiment on the R57 and R56 input contract."""
import argparse
import hashlib
import platform
import random
import sqlite3
from pathlib import Path
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from checkpoint import Reader, Pinned, Demand, make_snapshot, persist
from experiment import footprint
from bench import panels, prepare, save, load
from block_store import R56

HERE=Path(__file__).resolve().parent
ARMS={"cold":("cold",None),"full":("full",None),
      **{k+str(b):(k,b) for k in ("recent","largest","demand") for b in (1024,4096)}}
SEED=58041
REPS=3
# phase, read time, posting calls, batched body calls, posting bytes, body rows,
# body bytes, number of pinned event bodies, number of post-restart hot bodies.
FIELDS=("posting_calls","body_calls","posting_bytes","body_rows","body_bytes","pinned_bodies","hot_bodies")


def checkpoint_db(db):
    assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)


def run(ops,path,method):
    policy,cap=ARMS[method]
    goal=sum(op[0]=="w" for op in ops)//2
    demand=Demand() if policy=="demand" else None
    h=Reader(path,"shared",True)
    assert h.db.execute("PRAGMA synchronous").fetchone()==(2,)
    after=False;ordinal=0;post_q=0;latest=None;answers=[]
    times={"source_writes_ns":0,"demand_ns":0,"select_ns":0,"persist_ns":0}
    stats=dict(snapshot_write=0,snapshot_useful=0,snapshot_events=0,wal_bytes=0,
               pre_demand_py=0,meta_write_sql=0)
    while_idx=0
    for op in ops:
        if ordinal==goal and not after:
            base_path=Path(str(path)+"-wal")
            checkpoint_db(h.db)
            stats["before_checkpoint_bytes"]=path.stat().st_size
            if policy!="cold":
                if demand:stats["pre_demand_py"]=footprint(demand)
                start=perf_counter_ns()
                blob,count,nbytes=make_snapshot(h.hot.live,ordinal,latest,policy,cap,demand)
                times["select_ns"]=perf_counter_ns()-start
                start=perf_counter_ns();persist(h.db,blob);times["persist_ns"]=perf_counter_ns()-start
                stats.update(snapshot_write=len(blob),snapshot_useful=nbytes,snapshot_events=count,
                             wal_bytes=base_path.stat().st_size,meta_write_sql=4)
            start=perf_counter_ns();checkpoint_db(h.db);times["checkpoint_ns"]=perf_counter_ns()-start
            stats["after_checkpoint_bytes"]=path.stat().st_size
            h.close();demand=None
            start=perf_counter_ns();h=Pinned(path,policy!="cold");times["open_ns"]=perf_counter_ns()-start
            assert not h.rejected and h.fence==ordinal and len(h.pinned)==stats["snapshot_events"]
            assert h.loaded_bytes==stats["snapshot_write"]
            stats.update(snapshot_load=h.loaded_bytes,receipt_bytes=h.receipt_bytes,meta_open_sql=h.open_calls,
                         pinned_python_bytes=footprint((h.pinned,h.pinned_for)) if h.pinned else 0)
            after=True
        if op[0]=="q":
            _,anchor,tie,prior,expected=op
            start=perf_counter_ns();rank,work=h.read(anchor,tie,prior);ns=perf_counter_ns()-start
            assert rank==expected,(method,ordinal,anchor,rank,expected)
            if after:
                phase=1 if post_q<10 else 2
                answers.append((phase,ns,*work));post_q+=1
            else:
                pc,pbl,pb,bc,br,bb,hot,hit=work
                answers.append((0,ns,pc,bc,pb,br,bb,0,hot))
        else:
            _,j,rev,ids=op
            start=perf_counter_ns();ok=h.append(j,rev,ids);times["source_writes_ns"]+=perf_counter_ns()-start
            assert ok
            if demand is not None:
                start=perf_counter_ns();demand.append(ids);times["demand_ns"]+=perf_counter_ns()-start
            latest=rev;ordinal+=1
        while_idx+=1
    stats["end_cache_python_bytes"]=footprint((h.pinned,h.pinned_for,h.hot,h.complete))
    stats["events"]=ordinal;stats["fence"]=goal
    checkpoint_db(h.db);h.close()
    stats["database_bytes"]=path.stat().st_size
    return dict(times=times,stats=stats,queries=answers)


def aggregate(rows):
    out={}
    for panel in ("B","long"):
        for mode in ARMS:
            batches=[]
            for rep in range(REPS):
                ls=[r for r in rows if (r["panel"],r["method"],r["rep"])==(panel,mode,rep)]
                if not ls:continue
                assert len(ls)==(3 if panel=="long" else 6)
                values={k:sum(r["stats"][k] for r in ls) for k in ls[0]["stats"]}
                values.update({k:sum(r["times"][k] for r in ls) for k in ls[0]["times"]})
                queries=[q for r in ls for q in r["queries"]]
                for tag,which in (("pre",{0}),("first10",{1}),("later",{2}),("post",{1,2})):
                    q=[x for x in queries if x[0] in which]
                    values[tag+"_n"]=len(q)
                    values[tag+"_read_ns"]=sum(x[1] for x in q)
                    for i,name in enumerate(FIELDS):values[tag+"_"+name]=sum(x[i+2] for x in q)
                values["charged_bytes"]=sum(values[k] for k in ("snapshot_write","snapshot_load","receipt_bytes","post_posting_bytes","post_body_bytes"))
                values["end_to_end_ns"]=sum(values[k] for k in ("pre_read_ns","post_read_ns","source_writes_ns","demand_ns",
                    "select_ns","persist_ns","checkpoint_ns","open_ns"))
                batches.append(values)
            if not batches:continue
            merged={}
            for k,v in batches[0].items():
                vals=[row[k] for row in batches]
                if k.endswith("_ns") or k.endswith("_py") or k.endswith("_python_bytes"):
                    merged[k]=[int(median(vals)),vals]
                else:
                    assert all(v==u for u in vals),(k,vals)
                    merged[k]=v
            out[panel+"-"+mode]=merged
    return out


def protocol_digest():
    return hashlib.sha256((HERE/"PROTOCOL_RU.md").read_bytes().replace(b"\r\n",b"\n")).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    inp=load(R56/"durable/runs.json.gz")["oracle"]
    path=HERE/"runs.json.gz"
    if args.verify:
        raw=load(path)
        assert len(raw["runs"])==REPS*len(ARMS)*len(inp)
        assert raw["oracle"]==inp and raw["protocol"]==protocol_digest()
        assert aggregate(raw["runs"])==load(HERE/"results.json")
        print("Verified",len(raw["runs"]),"runs.");return
    prepared={};streams=panels()
    for p in ("B","long"):
        for repo,stream in streams[p].items():
            ops,digest=prepare(stream,p)
            assert inp[p+"/"+repo]==digest
            prepared[p,repo]=ops
    base=dict(oracle=inp,seed=SEED,protocol=protocol_digest(),python=sys.version,sqlite=sqlite3.sqlite_version,
              platform=platform.platform(),runs=[])
    raw=load(path) if path.exists() else base
    assert raw["oracle"]==inp and raw["protocol"]==protocol_digest()
    done={(r["panel"],r["project"],r["rep"],r["method"]) for r in raw["runs"]}
    rng=random.Random(SEED)
    with TemporaryDirectory(dir=HERE,prefix="measure-") as td:
        for rep in range(REPS):
            for (p,repo),ops in prepared.items():
                for position,name in enumerate(rng.sample(list(ARMS),len(ARMS))):
                    if (p,repo,rep,name) in done:continue
                    db=Path(td)/"one.sqlite"
                    row=run(ops,db,name);row.update(panel=p,project=repo,rep=rep,method=name,position=position)
                    raw["runs"].append(row);db.unlink()
            save(path,raw);save(HERE/"results.json",aggregate(raw["runs"]))
            print("Checkpoint block",rep+1,"of",REPS,flush=True)


if __name__=="__main__":
    main()
