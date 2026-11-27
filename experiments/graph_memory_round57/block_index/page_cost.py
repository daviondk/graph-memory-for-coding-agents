"""Checkpoint and page-accounting diagnostics in a separate untimed replay.

Pass --stats-python if the measuring interpreter lacks SQLite's dbstat virtual table.
That reader opens closed checkpointed files read-only and never changes their layout.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from bench import HERE, factory, load, panels, prepare, save
from frame_bench import open_store as frame_open
from frame_store import FRAME_MODES
from slab_bench import open_store as slab_open
from slab_store import NEW_MODES

MODES=("filelist","sealed_list",*NEW_MODES,*FRAME_MODES)


def accounting(path):
    url=path.resolve().as_uri()+"?mode=ro&immutable=1"
    db=sqlite3.connect(url,uri=True)
    pages,=db.execute("PRAGMA page_count").fetchone()
    free,=db.execute("PRAGMA freelist_count").fetchone()
    block,=db.execute("PRAGMA page_size").fetchone()
    tables={name:dict(pages=n,allocated=total,payload=payload,unused=unused) for name,n,total,payload,unused
            in db.execute("SELECT name,count(*),sum(pgsize),sum(payload),sum(unused) FROM dbstat GROUP BY name")}
    assert sum(item["allocated"] for item in tables.values())+free*block==pages*block==path.stat().st_size
    db.close()
    return dict(tables=tables,footprint=pages*block,free_pages=free,sqlite_reader=sqlite3.sqlite_version)


def snapshot(path,executable):
    result=subprocess.check_output([executable,"-B",str(Path(__file__).resolve()),"--inspect",str(path)])
    return json.loads(result)


def totals(records):
    result={}
    for panel in ("B","long"):
        for mode in MODES:
            rows=[r for r in records if (r["panel"],r["mode"])==(panel,mode)]
            assert len(rows)==(6 if panel=="B" else 3)
            out={}
            for key in ("before","after"):
                values=[r[key] for r in rows]
                counts=Counter()
                for v in values:
                    counts.update(standalone=v["footprint"],free_pages=v["free_pages"])
                    for item in v["tables"].values():counts.update(payload=item["payload"],unused=item["unused"])
                out[key]=dict(counts)
            out["vacuum_ms"]=sum(r["vacuum_ns"] for r in rows)/1e6
            result[panel+"-"+mode]=out
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inspect",type=Path);ap.add_argument("--stats-python",default=sys.executable)
    ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    if args.inspect:print(json.dumps(accounting(args.inspect)));return
    dest=HERE/"vacuum.json"
    if args.verify:
        raw=load(dest); assert totals(raw["records"])==raw["summary"]
        print("Verified page accounting for",len(raw["records"]),"databases.");return
    samples=panels();records=[]
    with TemporaryDirectory(dir=HERE,prefix="pages-") as td:
        for panel in ("B","long"):
            for repo,rows in samples[panel].items():
                ops,_=prepare(rows,panel)
                for mode in MODES:
                    path=Path(td)/"measure.sqlite"
                    if mode in FRAME_MODES:open_store=frame_open
                    elif mode in NEW_MODES:open_store=slab_open
                    else:open_store=factory
                    store=open_store(path,mode,True)
                    for op in ops:
                        if op[0]=="w":store.append(*op[1:])
                    assert store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
                    store.close()
                    b=snapshot(path,args.stats_python)
                    db=sqlite3.connect(path,isolation_level=None)
                    start=perf_counter_ns();db.execute("VACUUM")
                    assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
                    elapsed=perf_counter_ns()-start;db.close()
                    a=snapshot(path,args.stats_python)
                    path.unlink();records.append(dict(panel=panel,repo=repo,mode=mode,before=b,after=a,vacuum_ns=elapsed))
    summaries=totals(records)
    for k,v in summaries.items():
        source="frame" if k.split("-",1)[1] in FRAME_MODES else "slab"
        assert v["before"]["standalone"]==load(HERE/(source+"-results.json"))[k]["footprint"]
    save(dest,dict(records=records,summary=summaries))
    print("Verified",len(records),"primary SQLite sizes before compaction.")


if __name__=="__main__":
    main()
