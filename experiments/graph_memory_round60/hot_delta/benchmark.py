"""Paired timing with the cost of discovering hot evictions charged to consumers."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from pathlib import Path
from random import Random
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from hot_only import HERE, HotOnly
from coverage import Coverage, Hot, SketchPolicy, XOR, possible_losses, R59
from run_coverage import load, prepare, save
from lazy_reader import BlockStore
import sys
sys.path.insert(0, str(R59 / "fast_path"))
from fast_postings import Fast

MODES = ("exact", "append", "xor", "notify", "hot_checked", "hot_trusted")
CAPS = (1024, 4096)


def make(db, hot, cap):
    return {
        "exact": SketchPolicy(db, hot, None, cap),
        "append": Fast(db, hot, "append", cap),
        "xor": SketchPolicy(db, hot, XOR, cap),
        "notify": Coverage(db, hot, cap, True),
        "hot_checked": HotOnly(db, hot, cap, True),
        "hot_trusted": HotOnly(db, hot, cap, False),
    }


def replay(db, ops, rng, reference):
    fence = sum(op[0] == "w" for op in ops) // 2
    hot = Hot()
    arms = {}
    rows = []
    times = Counter()
    for op in ops:
        if not arms and db.next_id == fence:
            arms = {f"{cap}/{mode}": a for cap in CAPS for mode, a in make(db, hot, cap).items()}
        keys = rng.sample(list(arms), len(arms))
        if op[0] == "w":
            _, index, rev, members = op
            assert db.append(index, rev, members)
            if not arms:
                continue
            tracked = {}
            for key in keys:
                if hasattr(arms[key], "after_committed"):
                    start = perf_counter_ns()
                    tracked[key] = possible_losses(hot, members)
                    times[key] += perf_counter_ns() - start
            hot.append(index, members)
            for key in keys:
                start = perf_counter_ns()
                if key in tracked:
                    losses = [(j, body) for j, body in tracked[key].items() if j not in hot.live]
                    arms[key].after_committed(index, members, losses)
                else:
                    arms[key].after_write(index, members)
                times[key] += perf_counter_ns() - start
        elif arms:
            _, anchor, tie, prior, expected = op
            old = reference[len(rows)]
            assert (old["anchor"], old["prefix"]) == (anchor, db.next_id)
            out = {}
            for key in keys:
                start = perf_counter_ns()
                ans, stats = arms[key].read(anchor, tie, prior)
                elapsed = perf_counter_ns() - start
                assert ans == expected and arms[key].cache.size <= arms[key].cache.limit
                fields = ("posting_bytes", "body_bytes", "posting_calls", "body_calls")
                cost = [stats[field] for field in fields]
                if key in old["arms"]:
                    assert cost == [old["arms"][key].get(field, 0) for field in fields]
                out[key] = [*cost, elapsed, stats["stored_complement"]]
            rows.append(out)
    assert len(rows) == len(reference)
    return dict(reads=rows, update_ns=dict(times))


def run():
    old = load(HERE.parent / "coverage/runs.json.gz")["cases"]
    rng = Random(60091)
    raw = []
    panels = {"new": HERE.parent / "panel/events.json.gz", "r59": R59 / "holdout/events.json.gz"}
    workloads = {group + "/" + layout + "/" + name: prepare(changes, layout)[0]
                 for group, directory in panels.items() for name, changes in load(directory).items()
                 for layout in ("B", "long")}
    with TemporaryDirectory(dir=HERE) as tmp:
        path = Path(tmp) / "graph.sqlite"
        for block in range(3):
            batch = {}
            for case in rng.sample(sorted(workloads), len(workloads)):
                with closing(BlockStore(path, "filelist", True)) as db:
                    batch[case] = replay(db, workloads[case], rng, old[case]["logs"])
                path.unlink()
            raw.append(batch)
            print("Block", block + 1, "complete", flush=True)
    return raw


def summarize(raw):
    cols = ("posting_bytes", "body_bytes", "posting_calls", "body_calls", "read_ns", "admissions")
    groups = {}
    for group in ("new", "r59"):
        for layout in ("B", "long"):
            group_key = group + "/" + layout
            summary = groups[group_key] = {}
            for mode in MODES:
                for cap in CAPS:
                    label = f"{cap}/{mode}"
                    blocks = []
                    for batch in raw:
                        s = Counter()
                        for name, data in batch.items():
                            if not name.startswith(group_key + "/"):
                                continue
                            for row in data["reads"]:
                                s.update(dict(zip(cols, row[label])))
                            s["queries"] += len(data["reads"])
                            s["update_ns"] += data["update_ns"].get(label, 0)
                        s["combined_ns"] = s["read_ns"] + s["update_ns"]
                        s["charged"] = s["posting_bytes"] + s["body_bytes"]
                        blocks.append(s)
                    assert len({v["charged"] for v in blocks}) == 1
                    summary[label] = {k: [s[k] for s in blocks] for k in blocks[0]}
    return groups


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    path = HERE / "runs.json.gz"
    raw = load(path) if args.verify else run()
    result = summarize(raw)
    if args.verify:
        assert result == load(HERE / "results.json")
    else:
        save(path, raw)
        save(HERE / "results.json", result)
    for k, x in result["new/B"].items():
        print(k, x["charged"][0], round(median(x["combined_ns"]) / 1e6, 2))
