"""Cross posting representation with eviction order on real SQLite histories."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

from sieve import HERE, QueueCache
from coverage import Coverage, Hot, SketchPolicy, XOR, possible_losses, R59
from run_coverage import prepare, load, save
from lazy_reader import BlockStore


def case(db, ops):
    cut = sum(op[0] == "w" for op in ops) // 2
    rng = Random(60321)
    hot = Hot()
    policies = {}
    rows = []
    for op in ops:
        if not policies and db.next_id == cut:
            for quota in (1024, 4096):
                for queue in ("lru", "fifo", "sieve"):
                    for mode in ("exact", "xor", "notify"):
                        if mode == "notify":
                            reader = Coverage(db, hot, quota - 2, True)
                        else:
                            reader = SketchPolicy(db, hot, XOR if mode == "xor" else None, quota - 2)
                        if queue != "lru":
                            reader.cache = QueueCache(quota, queue, mode == "notify")
                        policies[f"{quota}/{queue}/{mode}"] = reader
        if op[0] == "w":
            _, j, rev, ids = op
            assert db.append(j, rev, ids)
            if policies:
                candidates = possible_losses(hot, ids)
                hot.append(j, ids)
                lost = [(p, v) for p, v in candidates.items() if p not in hot.live]
                for reader in policies.values():
                    if isinstance(reader, Coverage):
                        reader.after_committed(j, ids, lost)
                    else:
                        reader.after_write(j, ids)
        elif policies:
            _, f, tie, prior, expected = op
            measured = {}
            for name in rng.sample(list(policies), len(policies)):
                reader = policies[name]
                ans, stats = reader.read(f, tie, prior)
                assert ans == expected
                cache = reader.cache
                assert cache.size <= cache.limit
                measured[name] = [stats[k] for k in ("posting_bytes", "body_bytes", "posting_calls", "body_calls")]
            rows.append(measured)
    for reader in policies.values():
        reader.cache.inventory()
        if isinstance(reader.cache, QueueCache):
            reader.cache.serialized()
    return rows


def run():
    panels = {"new": HERE.parent / "panel/events.json.gz", "r59": R59 / "holdout/events.json.gz"}
    output = {}
    with TemporaryDirectory(dir=HERE) as temp:
        p = Path(temp) / "graph.sqlite"
        for group, archive in panels.items():
            for repo, events in load(archive).items():
                for layout in ("B", "long"):
                    ops, _ = prepare(events, layout)
                    with closing(BlockStore(p, "filelist", True)) as db:
                        output[f"{group}/{layout}/{repo}"] = case(db, ops)
                    p.unlink()
            print(group, "complete", flush=True)
    return output


def sums(raw):
    groups = {}
    for key, rows in raw.items():
        name = "/".join(key.split("/")[:2])
        tab = groups.setdefault(name, {})
        for r in rows:
            for arm, (p, b, pc, bc) in r.items():
                tab.setdefault(arm, Counter()).update(posting=p, bodies=b, calls=pc+bc, charged=p+b, queries=1)
    return groups


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    path = HERE / "runs.json.gz"
    raw = load(path) if args.verify else run()
    result = sums(raw)
    if args.verify:
        assert result == load(HERE / "results.json")
    else:
        save(path, raw)
        save(HERE / "results.json", result)
    print({k: v["charged"] for k,v in sorted(result["new/B"].items())})
