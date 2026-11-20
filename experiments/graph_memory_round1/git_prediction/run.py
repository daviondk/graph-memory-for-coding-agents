"""Frozen, prequential co-edit experiment. Python standard library only."""
import argparse
import collections
import datetime as dt
import functools
import hashlib
import json
import math
import os
import platform
import random
import re
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MIRRORS = HERE.parents[1] / "memory_session6" / "validity" / "mirrors"
METHODS = ["recency", "frequency", "lexical", "cochange", "raw_smoothed",
           "unit_smoothed", "fixed_mix", "online_mix"]


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args])


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changes(path, pin):
    data = git(path, "log", "--first-parent", "--diff-merges=first-parent",
               "--no-renames", "--name-status", "-z",
               "--format=%x00@@%H%x09%P%x09%ct%x00", pin["sha"])
    history = []
    for entry in re.split(rb"\x00@@(?=[a-f0-9]{40}\t)", data)[1:]:
        header, raw_paths = entry.split(b"\x00", 1)
        sha, parents, timestamp = header.decode("ascii").split("\t")
        fields = raw_paths.strip(b"\x00").split(b"\x00") if raw_paths.strip(b"\x00") else []
        assert len(fields) % 2 == 0
        touched, deleted = [], []
        for code, name in zip(fields[::2], fields[1::2]):
            code = code.strip().decode("ascii")
            assert code in ("A", "M", "D", "T"), code
            filename = name.decode("utf-8", "surrogateescape")
            if filename.endswith(".py"):
                (deleted if code == "D" else touched).append(filename)
        history.append((sha, parents.split(), int(timestamp), sorted(touched), sorted(deleted)))
    history.reverse()
    assert len(history) == pin["n_first_parent"]
    for previous, current in zip(history, history[1:]):
        assert current[1][0] == previous[0]
    return history[1:]


@functools.lru_cache(maxsize=50000)
def path_features(path):
    parts = path.lower().split("/")
    name = parts[-1][:-3]
    tokens = set(re.findall(r"[a-z]+|[0-9]+", name))
    return tokens, set(parts[:-1]), re.sub(r"(^tests?_|_tests?$)", "", name)


def jaccard(left, right):
    return len(left & right) / max(len(left | right), 1)


def normalize(values):
    denominator = sum(values.values())
    return {f: value / denominator for f, value in values.items()}


class Memory:
    def __init__(self):
        self.active = set()
        self.frequency = collections.Counter()
        self.last = {}
        self.raw = collections.defaultdict(collections.Counter)
        self.unit = collections.defaultdict(collections.Counter)
        self.weight = [1 / 3] * 3

    def score(self, anchor, index):
        files = sorted(self.active - {anchor})
        if not files:
            return {name: [] for name in METHODS}, []
        atokens, adirs, astem = path_features(anchor)
        prior_score = {}
        for file in files:
            tokens, dirs, stem = path_features(file)
            # Positive path prior; frequency contributes sublinearly.
            affinity = 2.5 * (bool(astem) and astem == stem) + 1.3 * jaccard(atokens, tokens)
            affinity += 0.7 * jaccard(adirs, dirs)
            prior_score[file] = math.exp(affinity) * (self.frequency[file] + 1) ** 0.5
        prior = normalize(prior_score)
        time_prior = normalize({f: (1 + index - self.last[f]) ** -0.7 for f in files})
        raw = self.raw.get(anchor, {})
        unit = self.unit.get(anchor, {})
        raw_smooth = {f: raw.get(f, 0) + 4 * prior[f] for f in files}
        unit_smooth = normalize({f: unit.get(f, 0) + 4 * prior[f] for f in files})
        experts = [prior, unit_smooth, time_prior]
        scores = {
            "recency": self.last, "frequency": self.frequency, "lexical": prior,
            "cochange": raw, "raw_smoothed": raw_smooth, "unit_smoothed": unit_smooth,
            "fixed_mix": {f: sum(q[f] for q in experts) / 3 for f in files},
            "online_mix": {f: sum(w * q[f] for w, q in zip(self.weight, experts)) for f in files},
        }
        top = {}
        for method, values in scores.items():
            if method == "cochange":
                top[method] = sorted(files, key=lambda f: (-values.get(f, 0), -prior[f],
                                                          -self.frequency[f], f))[:5]
            else:
                top[method] = sorted(files, key=lambda f: (-values[f], -self.frequency[f], f))[:5]
        return top, experts

    def outcome(self, experts, reachable):
        if not reachable:
            return
        factors = [math.exp(statistics.fmean(math.log(q[f]) for f in reachable)) for q in experts]
        products = [w * like for w, like in zip(self.weight, factors)]
        self.weight = [(1 - 1 / 32) * x / sum(products) + 1 / 96 for x in products]

    def observe(self, touched, deleted, index):
        self.active.difference_update(deleted)
        self.active.update(touched)
        self.frequency.update(touched)
        for f in touched:
            self.last[f] = index
        if 2 <= len(touched) <= 20:
            for origin in touched:
                for dest in touched:
                    if origin != dest:
                        self.raw[origin][dest] += 1
                        self.unit[origin][dest] += 1 / (len(touched) - 1)


def replay(pin, path, writer):
    events = changes(path, pin)
    half = len(events) // 2
    memory = Memory()
    before = sum(len(x[3]) >= 2 and len(x[3]) <= 20 for x in events[:half])
    summary = {"repo": pin["repo"], "changes": len(events), "train_changes": half,
               "train_queries": before}
    for i, (sha, parents, when, touched, deleted) in enumerate(events):
        if 2 <= len(touched) <= 20:
            key = f"{pin['repo']}:{i}".encode("utf-8")
            anchor = touched[int.from_bytes(hashlib.sha256(key).digest()) % len(touched)]
            targets = [f for f in touched if f != anchor]
            reachable = sorted(memory.active.intersection(targets))
            ranked, experts = memory.score(anchor, i)
            result = {}
            for name, top in ranked.items():
                assert anchor not in top and all(f in memory.active for f in top)
                result[name] = {"top5": top, "hits": len(set(top) & set(targets)),
                                "hit1": int(bool(top) and top[0] in targets)}
            row = {"repo": pin["repo"], "index": i, "sha": sha, "parent": parents[0], "unix": when,
                   "split": "warmup" if i < half else "evaluation", "anchor": anchor,
                   "targets": targets, "reachable": reachable, "anchor_seen": anchor in memory.active,
                   "candidates": len(memory.active - {anchor}), "weights_before": memory.weight,
                   "result": result}
            writer.write(json.dumps(row, separators=(",", ":")) + "\n")
            memory.outcome(experts, reachable)
        memory.observe(touched, deleted, i)
    summary.update({"paths_seen": len(memory.frequency), "active_end": len(memory.active),
                    "directed_edges": sum(len(v) for v in memory.unit.values())})
    return summary


def summarize(rows):
    def mean(values):
        return statistics.fmean(values)
    def group_obs(batch):
        return {"n": len(batch), "coverage": mean(len(r["reachable"]) / len(r["targets"]) for r in batch),
                "ranking": {m: {"r5": mean(r["result"][m]["hits"] / len(r["targets"]) for r in batch),
                                "h1": mean(r["result"][m]["hit1"] for r in batch)} for m in METHODS}}
    final = {}
    for split in ["warmup", "evaluation"]:
        part = [r for r in rows if r["split"] == split]
        by_repo = {repo: group_obs([r for r in part if r["repo"] == repo]) for repo in sorted({r["repo"] for r in part})}
        macro = {m: {k: mean(r["ranking"][m][k] for r in by_repo.values()) for k in ("r5", "h1")} for m in METHODS}
        diffs = [v["ranking"]["online_mix"]["r5"] - v["ranking"]["unit_smoothed"]["r5"] for v in by_repo.values()]
        rng = random.Random(20261118)
        samples = sorted(mean(rng.choices(diffs, k=len(diffs))) for _ in range(20000))
        final[split] = {"per_repo": by_repo, "event_weighted": group_obs(part), "macro": macro,
                        "macro_coverage": mean(v["coverage"] for v in by_repo.values()),
                        "delta_primary": mean(diffs), "bootstrap95": [samples[499], samples[19499]],
                        "signs_plus_equal_minus": [sum(d > 1e-12 for d in diffs),
                              sum(abs(d) <= 1e-12 for d in diffs), sum(d < -1e-12 for d in diffs)]}
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mirrors", type=Path, default=DEFAULT_MIRRORS)
    parser.add_argument("--out", type=Path, default=HERE / "run")
    args = parser.parse_args()
    for item in json.loads((HERE / "freeze.json").read_text(encoding="utf-8-sig")):
        assert hash_file(HERE / Path(item["Path"]).name).upper() == item["Hash"]
    pins = json.loads((HERE / "pins.json").read_text(encoding="utf-8-sig"))
    args.out.mkdir(parents=True, exist_ok=False)
    log_path = args.out / "predictions.jsonl"
    inventory = []
    with log_path.open("w", encoding="utf-8", newline="\n") as writer:
        for pin in pins:
            inventory.append(replay(pin, args.mirrors / pin["repo"], writer))
    summary = summarize([json.loads(line) for line in log_path.read_text().splitlines()])
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    metadata = {"utc_finish": dt.datetime.now(dt.timezone.utc).isoformat(), "python": sys.version,
                "git": git(HERE, "--version").decode().strip(), "platform": platform.platform(),
                "cpu_only": True, "manifest": inventory, "hashes": {
                    p.name: hash_file(p) for p in [Path(__file__), HERE / "pins.json", HERE / "PROTOCOL.md",
                                                   log_path, args.out / "summary.json"]}}
    (args.out / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary["evaluation"].items() if k != "per_repo"}, indent=2))


if __name__ == "__main__":
    main()
