"""Paired SQLite replays across old and new histories at four cache capacities."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from policy import Adaptive, R59, SketchPolicy, XOR
from admission import Governed
from bench_sketch import BlockStore, Policy, load, prepare, save, simulate

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
CAPS = (512, 1024, 2048, 4096)
MODES = ("exact", "xor", "joint", "gate", "adaptive", "self_only")


def readers(db, hot):
    arms = {}
    for cap in CAPS:
        arms[cap, "exact"] = SketchPolicy(db, hot, None, cap)
        arms[cap, "xor"] = SketchPolicy(db, hot, XOR, cap)
        arms[cap, "joint"] = Policy(db, hot, "joint", cap)
        arms[cap, "gate"] = Governed(db, hot, "gate", cap)
        arms[cap, "adaptive"] = Adaptive(db, hot, cap)
        arms[cap, "self_only"] = Adaptive(db, hot, cap, self_only=True)
    return arms


def sources():
    return {
        "old1": EXP / "graph_memory_round57/replication/events.json.gz",
        "old2": EXP / "graph_memory_round57/seed_pair/events.json.gz",
        "previous": R59 / "holdout/events.json.gz",
        "new": HERE.parent / "panel/events.json.gz",
    }


def measure(group):
    streams = load(sources()[group])
    result = {}
    with TemporaryDirectory(dir=HERE) as tmp:
        for name, changes in sorted(streams.items()):
            for layout in ("B", "long"):
                ops, receipt = prepare(changes, layout)
                path = Path(tmp) / "store.sqlite"
                with closing(BlockStore(path, "filelist", True)) as db:
                    rows = simulate(db, ops, readers)
                path.unlink()
                result[layout + "/" + name] = dict(rows=rows, oracle=receipt)
    return result


def summarize(parts):
    groups = {}
    sites = {}
    sums = ("posting_bytes", "body_bytes", "posting_calls", "body_calls", "selected_xor",
            "selected_full", "same_representation", "failed", "recovered1", "read_ns")
    for panel, raw in parts.items():
        for case, result in raw.items():
            layout, name = case.split("/", 1)
            group = panel + "/" + layout
            pub = groups.setdefault(group, {})
            by_project = sites.setdefault(group + "/" + name, {})
            for cap in CAPS:
                for mode in MODES:
                    key = f"{cap}/{mode}"
                    rows = [q["arms"][key] for q in result["rows"]]
                    assert all(q["resident"] <= cap for q in rows)
                    counts = {k: sum(q.get(k, 0) for q in rows) for k in sums}
                    counts.update(queries=len(rows), charged=counts["body_bytes"] + counts["posting_bytes"])
                    by_project[key] = counts
                    pub.setdefault(key, Counter()).update(counts)
    return dict(groups=groups, projects=sites)


def check_baselines(result):
    prior = load(R59 / "holdout/results.json")["sketch"]["groups"]
    previous = load(R59 / "reconcile/results.json")["groups"]
    old_panels = {"old1": "replication", "old2": "seed_pair", "previous": None}
    for group, old in old_panels.items():
        for layout in ("B", "long"):
            source = prior[layout] if old is None else previous[old + "-" + layout]
            for cap in (1024, 4096):
                for mode in ("xor", "exact", "joint"):
                    key = f"{cap}/{mode}"
                    row = result["groups"][group + "/" + layout][key]
                    fields = ("charged", "queries")
                    assert [row[m] for m in fields] == [source[key][m] for m in fields]


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    data = {}
    for group in sources():
        path = HERE / (group + "-queries.json.gz")
        if args.verify:
            data[group] = load(path)
        else:
            data[group] = measure(group)
            save(path, data[group])
        print(group, "complete", flush=True)
    result = summarize(data)
    check_baselines(result)
    if args.verify:
        assert result == load(HERE / "results.json")
    else:
        save(HERE / "results.json", result)
    for key in ("new/B", "new/long"):
        for cap in CAPS:
            print(key, cap, [result["groups"][key][f"{cap}/{m}"]["charged"] for m in MODES])
