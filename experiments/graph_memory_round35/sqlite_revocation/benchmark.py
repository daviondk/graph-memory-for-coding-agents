"""Replay two write schedules on separate on-disk SQLite databases."""
import gzip
import hashlib
import json
import os
import platform
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

D = Path(__file__).resolve().parent
SOURCE = D.parent/"deferred_revocation"
METHODS = ("exact", "before_read")
ROOT = Path("D:/CodexResearch/x20-bench-workspace/tmp")

def sha(b):
    return hashlib.sha256(b).hexdigest()

def load(p):
    b = p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix == ".gz" else b)

def save(p, value):
    b = json.dumps(value, sort_keys=True, separators=(",",":")).encode()
    p.write_bytes(gzip.compress(b, mtime=0) if p.suffix == ".gz" else b)

def schedule(log, policy):
    truth, persisted = set(), set()
    plan = []
    peak = 0
    for _, _, reads, added, removed in log:
        assert set(added).isdisjoint(removed)
        assert not (truth & set(added)) and set(removed) <= truth
        truth.update(added)
        truth.difference_update(removed)
        inserts = sorted(set(added) - persisted)
        persisted.update(inserts)
        pending = persisted - truth
        peak = max(peak, len(pending))
        deletes = sorted(pending) if policy == "exact" or reads else []
        persisted.difference_update(deletes)
        if reads:
            assert persisted == truth
        if inserts or deletes or reads:
            plan.append((inserts, deletes, (sorted(truth), len(reads)) if reads else None))
    plan.append(([], sorted(persisted-truth), (sorted(truth), 1)))
    return plan, peak

def execute(dbpath, plan):
    con = sqlite3.connect(dbpath, isolation_level=None)
    assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    con.execute("PRAGMA synchronous=FULL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.execute("CREATE TABLE edges (pair_id INTEGER PRIMARY KEY)")
    assert con.execute("PRAGMA page_size").fetchone()[0] == 4096
    assert con.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0, 0, 0)
    expected, observed = [], []
    writes = deletes = tx = 0
    start = time.perf_counter_ns()
    for ins, drop, read in plan:
        if ins or drop:
            con.execute("BEGIN IMMEDIATE")
            if ins: con.executemany("INSERT INTO edges VALUES (?)", [(x,) for x in ins])
            if drop: con.executemany("DELETE FROM edges WHERE pair_id = ?", [(x,) for x in drop])
            con.execute("COMMIT")
            tx += 1
            writes += len(ins)
            deletes += len(drop)
        if read is not None:
            ids, count = read
            for _ in range(count):
                observed.append([r[0] for r in con.execute("SELECT pair_id FROM edges ORDER BY pair_id")])
                expected.append(ids)
    before = time.perf_counter_ns()
    wal = Path(str(dbpath)+"-wal").stat().st_size
    check = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    end = time.perf_counter_ns()
    assert observed == expected and len(expected) == 5 and check == (0,0,0)
    assert con.total_changes == writes+deletes
    con.close()
    return {"ms":(end-start)/1e6, "before_checkpoint_ms":(before-start)/1e6, "tx":tx,
            "insert":writes, "delete":deletes, "wal":wal, "reads":len(expected),
            "observed":sha(json.dumps(observed,separators=(",",":")).encode())}

def main():
    seal = load(SOURCE/"forecast-seal.json")["files"]
    histories = {}
    for i in range(8):
        p = SOURCE/f"operations-{i}.json.gz"
        assert sha(p.read_bytes()) == seal[p.name]
        rows = load(p)
        assert histories.keys().isdisjoint(rows)
        histories.update(rows)
    assert len(histories) == 1207
    cohort = sorted(histories, key=lambda h:sha(("sqlite-revocation-v1/"+h).encode()))[:64]
    plans = {h:{k:schedule(histories[h]["log"], k) for k in METHODS} for h in cohort}
    plan = {"histories":cohort, "protocol":sha((D/"PROTOCOL_RU.md").read_bytes()), "program":sha(Path(__file__).read_bytes()),
            "source":sha((SOURCE/"forecast-seal.json").read_bytes()), "inputs":{k:v for k,v in seal.items() if k.startswith("operations-")},
            "sqlite":sqlite3.sqlite_version, "platform":platform.platform(), "python":sys.version, "volume":ROOT.drive,
            "page_size":4096, "journal":"WAL", "synchronous":"FULL"}
    save(D/"plan.json",plan)
    records = []
    with TemporaryDirectory(dir=ROOT) as scratch:
        for rep in range(4):
            ordered = sorted(cohort,key=lambda h:sha((str(rep)+"/"+h).encode()))
            for h in ordered:
                flip = (int(sha(("order/"+h).encode())[:8],16)+rep) % 2
                methods = reversed(METHODS) if flip else METHODS
                for k in methods:
                    with TemporaryDirectory(dir=scratch) as sample:
                        record = execute(Path(sample)/"edges.sqlite", plans[h][k][0])
                    records.append(dict(trajectory=h,method=k,rep=rep,peak=plans[h][k][1],**record))
    save(D/"runs.json.gz",records)
    results = summarize(records, cohort)
    save(D/"results.json", {"summaries":results,"measurements":len(records),"plan":sha((D/"plan.json").read_bytes()),
                           "runs":sha((D/"runs.json.gz").read_bytes())})

def summarize(records, cohort):
    panels = {}
    samples = defaultdict(list)
    for r in records: samples[r["trajectory"],r["method"]].append(r)
    for h in cohort:
        x,y = (samples[h,k] for k in METHODS)
        assert len(x)==len(y)==4
        assert len({r["observed"] for r in [*x,*y]})==1
    rng = np.random.default_rng(350914)
    ix = rng.integers(len(cohort), size=(10000,len(cohort)))
    for key in ("ms","before_checkpoint_ms","tx","delete","insert","wal"):
        mat = np.array([[statistics.median(r[key] for r in samples[h,k]) for k in METHODS] for h in cohort])
        a,b = mat.mean(axis=0)
        ma,mb = mat[ix,:].mean(axis=1).T
        panels[key] = {"means":[a,b],"delta":a-b,"ci":np.quantile(ma-mb,[.025,.975]).tolist(),
                       "ratio":a/b,"ratio_ci":np.quantile(ma/mb,[.025,.975]).tolist(),
                       "direction_counts":[int(fn(mat[:,0],mat[:,1]).sum()) for fn in (np.greater,np.equal,np.less)]}
    panels["histories_with_deferred_deletions"] = sum(samples[h,"before_read"][0]["peak"]>0 for h in cohort)
    return panels

if __name__ == "__main__":
    main()

