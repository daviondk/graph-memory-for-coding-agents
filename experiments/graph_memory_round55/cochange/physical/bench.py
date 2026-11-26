"""Randomized paired elapsed-time blocks. No sleep and no synthetic query work."""
import argparse
from collections import Counter
import os
from pathlib import Path
import platform
import random
import sqlite3
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from extract import read_json, write_json
sys.path.insert(0, str(HERE.parent))
from replay import Graph, Controller

PLANS = ("classic8", "classic9", "partial8", "classic13", "partial12")
SEED = 55491
DDL = """CREATE TABLE source(q TEXT NOT NULL,cid INTEGER NOT NULL,score INTEGER NOT NULL,
         PRIMARY KEY(q,cid)) WITHOUT ROWID; CREATE INDEX ix_rank ON source(q,score DESC,cid);"""

class Rows(list):
    def fetchall(self):
        return self

class ReadTimer:
    """Instrument the two ordered read sites. End timer after Python tuples exist."""
    def __init__(self, db):
        self.db = db
        self.nanos = 0
        self.calls = self.rows = 0
    def execute(self, sql, params):
        start = perf_counter_ns()
        rows = self.db.execute(sql,params).fetchall()
        self.nanos += perf_counter_ns()-start
        self.calls += 1
        self.rows += len(rows)
        return Rows(rows)

def workload(source):
    out={}
    for q,stream in source.items():
        paths = [p if len(p)<=64 else [] for _,p in stream["revisions"]]
        scores = []
        ids = {}
        for t, names in enumerate(paths):
            for p in names:
                ids.setdefault(p, len(ids))
            if t < 63:
                continue
            by_id = dict.fromkeys(ids.values(),0)
            for ps in paths[t-31:t+1]:
                for p in ps:
                    by_id[ids[p]] += len(ps)-1
            scores.append(tuple(sorted(by_id.items(),key=lambda z:(-z[1],z[0]))[:8]))
        out[q]=(paths,scores)
    return out

def initialize(filename, storage, paths):
    db = sqlite3.connect(filename)
    if storage=="wal":
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()==("wal",)
        db.execute("PRAGMA synchronous=FULL")
    db.executescript(DDL)
    graph = Graph(db)
    for t in range(64):
        graph.apply(paths[t],paths[t-32] if t>=32 else [],t)
    db.commit()
    return db,graph

def run(work, name, storage, filename, timed_reads):
    paths, oracle = work
    db,graph = initialize(filename,storage,paths)
    reader = ReadTimer(db) if timed_reads else db
    mode = "classic" if name.startswith("classic") else "partial"
    capacity = int(name[len(mode):])
    cold_start = perf_counter_ns()
    state = Controller(reader,capacity,mode)
    cold_control = perf_counter_ns()-cold_start
    cold_sql = reader.nanos if timed_reads else 0
    cold_reads = reader.calls if timed_reads else 0
    cold_rows = reader.rows if timed_reads else 0
    assert state.state[0][:8]==oracle[0]
    packets = []
    start = perf_counter_ns()
    for t in range(64,len(paths)):
        dirty, _ = graph.apply(paths[t],paths[t-32],t)
        packets.append(state.step(dirty))
        db.commit()
    elapsed = perf_counter_ns()-start
    assert packets == oracle[1:]
    db.close()
    return {"full_ns":elapsed, "cold_control_ns":cold_control, "cold_sql_ns":cold_sql,
            "index_ns":reader.nanos-cold_sql if timed_reads else 0,
            "warm_calls":reader.calls-cold_reads if timed_reads else 0,
            "warm_rows":reader.rows-cold_rows if timed_reads else 0}

def main(scratch):
    rng = random.Random(SEED)
    source = read_json(HERE.parent/"commits.json.gz")
    work = workload(source)
    logical = read_json(HERE.parent/"results.json")["results"]["32"]["projects"]
    samples = []
    sequence = 0
    with TemporaryDirectory(dir=scratch) as folder:
        scratch_db = Path(folder)
        for rep in range(-1,7):
            modes = ["memory","wal"]
            rng.shuffle(modes)
            for storage in modes:
                names = list(work)
                rng.shuffle(names)
                for q in names:
                    plans = list(PLANS)
                    rng.shuffle(plans)
                    for name in plans:
                        sequence += 1
                        # Fresh database; never time cleanup or opening/creating schema.
                        filename = ":memory:" if storage=="memory" else str(scratch_db/f"db-{sequence}.sqlite")
                        stats = run(work[q],name,storage,filename,False)
                        if storage=="wal":
                            Path(filename).unlink()
                        # Measure ordered reads independently of the main timing. Run on every block.
                        times = run(work[q],name,storage,filename,True)
                        if storage=="wal":
                            Path(filename).unlink()
                        assert [times["warm_calls"],times["warm_rows"]] == logical[q]["costs"][name]["warm"]
                        if rep>=0:
                            stats.update({k:times[k] for k in ("index_ns","cold_sql_ns","warm_calls","warm_rows")})
                            samples.append([rep,storage,q,name,sequence,stats])
                print(rep,storage,flush=True)
    write_json(HERE/"timings.json.gz", {"runs":samples,"seed":SEED,"python":sys.version,
        "sqlite":sqlite3.sqlite_version, "os":platform.platform(),"cpu":platform.processor(),
        "storage_path_drive":os.path.splitdrive(str(scratch.resolve()))[0]},False)

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--scratch",type=Path,required=True)
    main(ap.parse_args().scratch)
