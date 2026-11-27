"""Prequential replay, exact integration over anchors, and repository-blocked estimates."""
import argparse
import gzip
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean

HERE = Path(__file__).resolve().parent
R56 = HERE.parents[1] / "graph_memory_round56"
sys.path.insert(0, str(R56 / "event_intersection"))
from evaluate import panels
from risk import WEIGHTS, replay


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def output(path, data, verify):
    if verify:
        assert read(path) == data, path
    else:
        raw = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
        path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)


def summarize(records):
    methods = defaultdict(Counter)
    differences = []
    for row in records:
        observed = row["ids"]
        n = len(observed)
        target = set(observed)
        per_commit = Counter()
        for a in observed:
            answers = row["answers"][str(a)]
            for reader, (event_count, member_count, idx) in answers["readers"].items():
                for column, weight in enumerate(WEIGHTS):
                    packet = answers["packets"][idx[column]]
                    assert a not in packet and len(packet) == len(set(packet))
                    hits = len(target.intersection(packet))
                    name = f"{reader}/{weight}"
                    method = methods[name]
                    method["anchors"] += 1
                    method["event_reads"] += event_count
                    method["member_reads"] += member_count
                    method["hit_anchors"] += hits > 0
                    method["incidence_sum"] += hits / (n - 1)
                    per_commit[name] += hits
                if reader == "fill6":
                    methods["fill6/commit"]["changed_ranks"] += idx[1] != idx[2]
        for name, hits in per_commit.items():
            methods[name]["commit_sum"] += hits / (n * (n - 1))
            methods[name]["commits"] += 1
        delta_hits = per_commit["fill6/commit"] - per_commit["fill6/companion"]
        differences.append(delta_hits)
    aggregate = {}
    for name, counts in methods.items():
        aggregate[name] = dict(counts)
        aggregate[name]["commit_recall"] = counts["commit_sum"] / counts["commits"]
        aggregate[name]["incidence_recall"] = counts["incidence_sum"] / counts["anchors"]
    return dict(methods=aggregate, wins=sum(x > 0 for x in differences), ties=differences.count(0),
                losses=sum(x < 0 for x in differences))


def contrast(projects, metric="commit_recall"):
    deltas = []
    for v in projects.values():
        if v["methods"]:
            a, b = (v["methods"]["fill6/" + w] for w in ("commit", "companion"))
            deltas.append(100 * (a[metric] - b[metric]))
    rng = random.Random(57104)
    draws = sorted(fmean(rng.choices(deltas, k=len(deltas))) for _ in range(20000))
    return {"repo_macro_delta_pp": fmean(deltas), "interval_pp": [draws[499], draws[19499]],
            "projects": len(deltas), "wins": sum(d > 0 for d in deltas), "losses": sum(d < 0 for d in deltas)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("panel", choices=("new", "old"))
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()
    datasets = ({"new": read(HERE.parent / "replication" / "events.json.gz")}
                if args.panel == "new" else panels())
    totals = {}
    for panel, data in datasets.items():
        records = {}
        for repo, stream in data.items():
            def eligible(t, sha):
                if panel == "new":
                    return t >= len(stream) // 2
                if panel == "long":
                    return t >= len(stream) // 2 and int(sha, 16) % 11 == 0
                return t >= 64
            records[repo] = replay(stream, eligible)
        projects = {repo: summarize(rows) for repo, rows in records.items()}
        pooled = summarize([row for rs in records.values() for row in rs])
        totals[panel] = dict(projects=projects, pooled=pooled,
                             commit=contrast(projects), incidence=contrast(projects, "incidence_recall"))
        output(HERE / f"{panel}-ranks.json.gz", records, args.verify)
        print(panel, pooled["methods"]["fill6/commit"]["commits"], totals[panel]["commit"], flush=True)
    output(HERE / f"{args.panel}-metrics.json", totals, args.verify)


if __name__ == "__main__":
    main()
