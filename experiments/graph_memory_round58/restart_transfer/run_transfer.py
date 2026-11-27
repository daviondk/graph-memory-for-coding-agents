"""Rerun the registered R58 SQLite restart study on external frozen Git streams."""
import argparse
import hashlib
from pathlib import Path
import random
import sqlite3
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
R57 = HERE.parents[1] / "graph_memory_round57"
sys.path.insert(0, str(HERE.parent / "restart"))
from bench_restart import ARMS, FIELDS, load, prepare, run, save
from evaluate import chosen

GROUPS = ("replication", "seed_pair")
WORKLOADS = ("long", "B")
SEED = 58171


def source(group):
    base = R57 / group
    streams = load(base / "events.json.gz")
    heads = load(base / "heads.json")
    assert len(streams) == len(heads) == 6 and set(streams) == set(heads)
    assert all(s[-1][0] == heads[k]["head"] for k, s in streams.items())
    return streams, heads


def identifiers(stream, workload):
    out = []
    for t, (sha, names) in enumerate(stream):
        paths = names if len(names) <= 64 else []
        anchor = chosen(workload, sha, t, len(stream), paths)
        if anchor is not None:
            out.append([t, sha, anchor])
    return out


def digest(path, normalise=False):
    b = path.read_bytes()
    return hashlib.sha256(b.replace(b"\r\n", b"\n") if normalise else b).hexdigest()


def count(stats, rows):
    post = [r for r in rows if r[0] in (1, 2)]
    work = {field: sum(r[i+2] for r in post) for i, field in enumerate(FIELDS)}
    one_way = stats["snapshot_write"]
    assert one_way == stats["snapshot_load"]
    charged = 2 * one_way + stats["receipt_bytes"] + work["posting_bytes"] + work["body_bytes"]
    return dict(queries=len(rows), post=len(post), charged=charged, selected=stats["snapshot_events"],
                useful=stats["snapshot_useful"], written=one_way, receipt=stats["receipt_bytes"],
                wal=stats["wal_bytes"], db=stats["database_bytes"], **work)


def run_all():
    protocol = digest(HERE/"PROTOCOL_RU.md", True)
    archive = {g:digest(R57/g/"events.json.gz") for g in GROUPS}
    raw_path = HERE/"runs.json.gz"
    data = (load(raw_path) if raw_path.exists() else
            dict(protocol=protocol, sources=archive, sqlite=sqlite3.sqlite_version,
                 python=sys.version, seed=SEED, projects={}))
    assert data["protocol"] == protocol and data["sources"] == archive
    randomizer = random.Random(SEED)
    with TemporaryDirectory(dir=HERE, prefix="sqlite-") as directory:
        for group in GROUPS:
            streams, heads = source(group)
            for project, stream in sorted(streams.items()):
                key = group+"/"+project
                case = data["projects"].setdefault(key, dict(head=heads[project]["head"],
                                                           commits=len(stream), workloads={}))
                for workload in WORKLOADS:
                    order = randomizer.sample(list(ARMS), len(ARMS))
                    if workload in case["workloads"]:
                        continue
                    ops, oracle = prepare(stream, workload)
                    q = identifiers(stream, workload)
                    n_events = sum(op[0] == "w" for op in ops)
                    assert n_events >= 2, "Frozen archives have nonempty midpoint prefixes"
                    assert len(q) == sum(op[0] == "q" for op in ops)
                    row = dict(events=n_events, fence=n_events//2, oracle=oracle, ids=q, arms={})
                    for mode in order:
                        path = Path(directory)/"run.sqlite"
                        observed = run(ops, path, mode)
                        stats = observed["stats"]
                        records = observed["queries"]
                        # Keep per-query SQLite work without using noisy timings as a replication.
                        work = [[r[0], *r[2:]] for r in records]
                        row["arms"][mode] = dict(summary=count(stats, records), work=work)
                        path.unlink()
                        assert not list(Path(directory).iterdir())
                    case["workloads"][workload] = row
                    save(raw_path, data)
                    print(group, project, workload, len(q), flush=True)
    return data


def aggregate(data):
    result = {}
    for workload in WORKLOADS:
        result[workload] = {}
        for group in (*GROUPS, "both"):
            rows = {k:v["workloads"][workload] for k,v in data["projects"].items()
                    if group == "both" or k.startswith(group+"/")}
            summary = {}
            for name in ARMS:
                metrics = [r["arms"][name]["summary"] for r in rows.values()]
                summary[name] = {key:sum(m[key] for m in metrics) for key in metrics[0]}
            contrasts = {}
            for comparator in ("recent1024","largest1024","cold","full"):
                differences = {k:r["arms"]["demand1024"]["summary"]["charged"]
                               -r["arms"][comparator]["summary"]["charged"] for k,r in rows.items()}
                contrasts[comparator] = dict(deltas=differences, sum=sum(differences.values()),
                    win=sum(x<0 for x in differences.values()), tie=sum(x==0 for x in differences.values()),
                    loss=sum(x>0 for x in differences.values()))
            result[workload][group] = dict(arms=summary, contrasts=contrasts)
    return result


def main():
    parser = argparse.ArgumentParser();parser.add_argument("--verify", action="store_true")
    verify = parser.parse_args().verify
    if verify:
        data = load(HERE/"runs.json.gz")
        assert data["protocol"] == digest(HERE/"PROTOCOL_RU.md",True)
        assert data["sources"] == {g:digest(R57/g/"events.json.gz") for g in GROUPS}
        assert aggregate(data) == load(HERE/"results.json")
    else:
        data = run_all()
        save(HERE/"results.json",aggregate(data))
    n = sum(len(r["arms"]) for p in data["projects"].values() for r in p["workloads"].values())
    assert n == 192
    print(n, "real SQLite runs")


if __name__ == "__main__":
    main()
