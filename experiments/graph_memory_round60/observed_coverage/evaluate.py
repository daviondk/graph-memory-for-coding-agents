"""Apply graph complements to the same editor actions and compare each control read."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "observed"))
from replay import BLOCKS, CAPS, Hot, SketchPolicy, XOR, coordinates, run, charge, save, load
sys.path.insert(0, str(HERE.parent / "hot_delta"))
from hot_only import HotOnly
from coverage import Coverage, possible_losses

MODES = ("exact", "xor", "notify", "hot_trusted")


def readers(db):
    hot = Hot()
    arms = {}
    for cap in CAPS:
        arms[cap, "exact"] = SketchPolicy(db, hot, None, cap)
        arms[cap, "xor"] = SketchPolicy(db, hot, XOR, cap)
        arms[cap, "notify"] = Coverage(db, hot, cap, True)
        arms[cap, "hot_trusted"] = HotOnly(db, hot, cap, False)
    return hot, arms


def publish(hot, arms, j, files):
    before = possible_losses(hot, files)
    hot.append(j, files)
    gone = [(n, values) for n, values in before.items() if n not in hot.live]
    for (_, mode), arm in arms.items():
        if mode in ("notify", "hot_trusted"):
            arm.after_committed(j, files, gone)
        else:
            arm.after_write(j, files)
        assert arm.cache.size <= arm.cache.limit


def score(raw, original):
    result = {}
    for span, sessions in raw.items():
        baseline = original[span]
        assert len(sessions) == len(baseline) == 108
        for cap in CAPS:
            key = f"{span}/{cap}"
            sums = defaultdict(Counter)
            diffs = defaultdict(Counter)
            for obs, old in zip(sessions, baseline):
                assert (obs["actor"], obs["issue"], len(obs["rows"])) == (old["actor"], old["issue"], len(old["rows"]))
                for row, ref in zip(obs["rows"], old["rows"]):
                    assert row["rank"] == ref["rank"] and row["window"] == ref["window"]
                    measures = {m: row["arms"][f"{cap}/{m}"] for m in MODES}
                    for m, q in measures.items():
                        if m in ("exact", "xor"):
                            assert q == ref["arms"][f"{cap}/{m}"]
                        sums[m].update(query=1, charged=charge(q), calls=q.get("body_calls", 0) + q.get("posting_calls", 0))
                for m in MODES:
                    diffs[obs["issue"]][m] += sum(charge(q["arms"][f"{cap}/{m}"]) -
                                                    charge(q["arms"][f"{cap}/exact"]) for q in obs["rows"])
            result[key] = dict(methods=sums, issue_delta_from_full=diffs)
    return result


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    traces = coordinates()
    raw = {}
    with TemporaryDirectory(dir=HERE) as tmp:
        for span in BLOCKS:
            group = raw[str(span)] = []
            for tr in traces:
                p = Path(tmp) / "observed.sqlite"
                group.append(run(p, tr, span, readers, publish))
                p.unlink()
    raw = json.loads(json.dumps(raw))
    results = score(raw, load(HERE.parent / "observed/queries.json.gz"))
    for fname, obj in (("queries.json.gz", raw), ("results.json", results)):
        if args.verify:
            assert load(HERE / fname) == obj
        else:
            save(HERE / fname, obj)
    for key, row in results.items():
        print(key, [row["methods"][m]["charged"] for m in MODES])
