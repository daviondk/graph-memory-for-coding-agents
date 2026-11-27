"""Paired, single-writer WAL replays on the pinned Round 56 streams."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from math import ceil
from pathlib import Path
import platform
import random
import sqlite3
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from block_store import ARMS, EXTRA, BLOCK, BlockStore, R56
from benchmark import panels, prepare
from store import Store

HERE = Path(__file__).resolve().parent
MODES = ("full", "own", "split", *ARMS)
SEED = 57061
REPETITIONS = 5


def save(path, value):
    blob = (json.dumps(value, sort_keys=True, separators=(",",":")) + "\n").encode()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(gzip.compress(blob, mtime=0) if path.suffix == ".gz" else blob)
    tmp.replace(path)


def load(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def protocol_digest(path):
    data=path.read_bytes().replace(b"\r\n",b"\n")
    return hashlib.sha256(data).hexdigest()


def factory(path, mode, create=False):
    return (BlockStore if mode in (*ARMS,*EXTRA) else Store)(path, mode, create=create)


def run(ops, path, mode, open_store=factory, source_counters=False):
    start=perf_counter_ns()
    st=open_store(path,mode,True)
    init=perf_counter_ns()-start
    assert st.db.execute("PRAGMA synchronous").fetchone()[0] == 2
    timings=[]; reads=[]; counts=Counter()
    for op in ops:
        if op[0]=="q":
            _,anchor,tie,prior,expected=op
            start=perf_counter_ns()
            value,(calls,nrows,payload)=st.read(anchor,tie,prior)
            reads.append(perf_counter_ns()-start)
            assert value==expected,(mode,anchor,value,expected)
            counts.update(queries=1,sql=calls,event_rows=nrows,event_bytes=payload)
        else:
            _,j,rev,ids=op
            start=perf_counter_ns()
            done=st.append(j,rev,ids)
            timings.append(perf_counter_ns()-start)
            assert done
            counts.update(events=1,members=len(ids))
    if source_counters:
        counts["source_blobs"]=getattr(st,"src_blobs",counts["event_rows"])
        counts["source_rows"]=getattr(st,"src_rows",counts["event_rows"])
        counts["source_bytes"]=getattr(st,"src_bytes",counts["event_bytes"])
    counts["metadata_rows"]=getattr(st,"metadata_rows",0)
    counts["metadata_bytes"]=getattr(st,"metadata_bytes",0)
    counts["row_changes"]=st.db.total_changes
    counts["tail_events"]=len(getattr(st,"tail",{}))
    counts["resident_incident_refs"]=sum(len(js) for js in getattr(st,"incident",{}).values())
    counts["owner_refs"]=sum(len(js) if mode=="split" else len(js[0]) for js in getattr(st,"owned",{}).values())
    if mode=="split":
        counts["resident_event_bodies"]=len(st.live)
    elif mode=="own":
        counts["resident_event_bodies"]=len({j for tail,_ in st.owned.values() for j,_ in tail})
    else:
        counts["resident_event_bodies"]=counts["tail_events"]
    names=[n for n, in st.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    counts["index_rows"]=sum(st.db.execute("SELECT COUNT(*) FROM "+n).fetchone()[0] for n in names if n not in ("event","slab","frame","tail"))
    start=perf_counter_ns(); checkpoint=st.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    cp=perf_counter_ns()-start
    assert checkpoint==(0,0,0)
    st.close()
    size=path.stat().st_size
    start=perf_counter_ns(); reopened=open_store(path,mode); restore=perf_counter_ns()-start
    assert reopened.next_id==len(timings)
    counts.update(restore_rows=reopened.restore_rows,restore_payload=reopened.restore_payload)
    if source_counters:
        counts["restart_source_bytes"]=getattr(reopened,"restore_source_bytes",reopened.restore_payload)
    reopened.close()
    return dict(writes=timings,reads=reads,create_ns=init,checkpoint_ns=cp,reopen_ns=restore,size=size,counts=dict(counts))


def percentile(seq,fraction):
    return sorted(seq)[ceil(len(seq)*fraction)-1]


def aggregate(runs,modes=MODES):
    result={}
    for panel in ("B","long"):
        for mode in modes:
            groups=[]
            for rep in range(REPETITIONS):
                rows=[r for r in runs if (r["panel"],r["mode"],r["rep"])==(panel,mode,rep)]
                if not rows:continue
                assert len(rows)==(6 if panel=="B" else 3)
                writes=[v for r in rows for v in r["writes"]]
                boundary=[v for r in rows for i,v in enumerate(r["writes"]) if (i+1)%(8 if mode in ("plain8","compressed8") else BLOCK)==0]
                reads=[v for r in rows for v in r["reads"]]
                counts=dict(sum((Counter(r["counts"]) for r in rows),Counter()))
                groups.append(dict(footprint=sum(r["size"] for r in rows),counts=counts,
                    write_ns=sum(writes),read_ns=sum(reads),mixed_ns=sum(writes)+sum(reads),
                    restart_ns=sum(r["reopen_ns"] for r in rows),create_ns=sum(r["create_ns"] for r in rows),
                    checkpoint_ns=sum(r["checkpoint_ns"] for r in rows),p50_write_ns=percentile(writes,.5),
                    p95_write_ns=percentile(writes,.95),p99_write_ns=percentile(writes,.99),
                    p50_seal_ns=percentile(boundary,.5),p99_seal_ns=percentile(boundary,.99)))
            if not groups:continue
            assert all(g["footprint"]==groups[0]["footprint"] and g["counts"]==groups[0]["counts"] for g in groups)
            result[panel+"-"+mode]=dict(footprint=groups[0]["footprint"],counts=groups[0]["counts"],
                times={k:[int(median(g[k] for g in groups)),[g[k] for g in groups]]
                       for k in groups[0] if k.endswith("_ns")})
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    path=HERE/"runs.json.gz"
    paths=panels()
    inputs={}; keys={}
    for panel in ("B","long"):
        for repo,rows in paths[panel].items():
            inputs[panel,repo],signature=prepare(rows,panel)
            keys[panel+"/"+repo]=signature
    assert keys==load(R56/"durable/runs.json.gz")["oracle"]
    if args.verify:
        raw=load(path)
        assert raw["oracle"]==keys and len(raw["runs"])==len(inputs)*len(MODES)*REPETITIONS
        assert raw["protocol_sha256"]==protocol_digest(HERE/"PROTOCOL_RU.md")
        assert aggregate(raw["runs"])==load(HERE/"results.json")
        print("Verified",len(raw["runs"]),"runs and",len(keys),"R56 oracle digests.")
        return
    raw=load(path) if path.exists() else dict(seed=SEED,python=sys.version,sqlite=sqlite3.sqlite_version,
        platform=platform.platform(),protocol_sha256=protocol_digest(HERE/"PROTOCOL_RU.md"),
        oracle=keys,runs=[])
    assert raw["oracle"]==keys
    done={(r["panel"],r["repo"],r["rep"],r["mode"]) for r in raw["runs"]}
    rng=random.Random(SEED)
    with TemporaryDirectory(dir=HERE,prefix="tmp-") as td:
        for rep in range(REPETITIONS):
            for panel,repo in inputs:
                for pos,mode in enumerate(rng.sample(MODES,len(MODES))):
                    key=(panel,repo,rep,mode)
                    if key in done:continue
                    db=Path(td)/"replay.sqlite"
                    row=run(inputs[panel,repo],db,mode)
                    row.update(panel=panel,repo=repo,rep=rep,mode=mode,position=pos)
                    raw["runs"].append(row);db.unlink()
            save(path,raw);save(HERE/"results.json",aggregate(raw["runs"]))
            print("paired block",rep+1,"/",REPETITIONS,"saved",flush=True)


if __name__=="__main__":
    main()
