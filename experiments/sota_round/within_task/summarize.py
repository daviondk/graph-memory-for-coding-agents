"""Aggregate frozen within-trajectory decisions including abstentions."""
import csv
import gzip
import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import numpy as np
from memory import ARMS

HERE = Path(__file__).resolve().parent
METRICS = {"target": 2, "exact": 1, "family": 4}


def lines(name):
    with gzip.open(HERE/name, "rt", encoding="utf8") as f:
        yield from map(json.loads, f)


def dump(path, obj):
    (HERE/path).write_text(json.dumps(obj, indent=2), encoding="utf8")


def main():
    index = {}
    repo_set = set()
    stored = Counter()
    totals = Counter()
    all_histories = list(lines("histories.jsonl.gz"))
    for h in all_histories:
        _, lang, repo, sid, _ = h["path"].split("/")
        assert sid not in index
        index[sid] = repo
        repo_set.add(repo)
        stored.update(h["stored_bytes"])
        totals.update(h["counts"])
        for key in ("pairs", "success", "all", "source_bytes"):
            totals["total_" + key] += h[key]
    repos = sorted(repo_set)
    cohort = defaultdict(Counter)
    per_repo = {r: Counter() for r in repos}
    population = Counter()
    cohort_histories = defaultdict(set)
    cohort_repos = defaultdict(set)
    delivered = defaultdict(Counter)
    for r in lines("decisions.jsonl.gz"):
        sid, repo = r["sid"], index[r["sid"]]
        population["triggers"] += 1
        population["recurrent_triggers"] += int(r["recurrent"])
        population["fp_recurrent_triggers"] += int(r["fp_recurrent"])
        population["no_pairs"] += int(not r["n_pair"])
        population["no_success"] += int(not r["n_success"])
        for arm, sizes in r["sent_bytes"].items():
            delivered["all_triggers"][arm+"_1"] += sum(sizes[:1])
            delivered["all_triggers"][arm+"_3"] += sum(sizes)
        if r["branch"] != "labelled":
            continue
        groups = ["all_labelled"]
        if r["recurrent"]:
            groups.append("primary")
            if r["gold"]["target"] and r["gold"]["family"]:
                groups.append("primary_extractable")
        if r["fp_recurrent"]:
            groups.append("fingerprint_recurrent")
        if not r["n_pair"]:
            groups.append("no_prior_pair")
        if not r["recurrent"]:
            groups.append("without_recurrence")
        if r["n_pair"]:
            groups.append("any_prior_pair")
        for g in groups:
            cohort_histories[g].add(sid)
            cohort_repos[g].add(repo)
            c = cohort[g]
            c["n"] += 1
            c["gold_extractable"] += int(bool(r["gold"]["family"] and r["gold"]["target"]))
            c["available_target"] += int(r["any_success_target"])
            c["available_exact"] += int(r["any_success_exact"])
            for arm, flags in r["hits"].items():
                c[arm+"_abstain"] += int(not flags)
                c[arm+"_returned3"] += len(flags)
                sizes = r["sent_bytes"][arm]
                delivered[g][arm+"_1"] += sum(sizes[:1])
                delivered[g][arm+"_3"] += sum(sizes)
                for k in (1, 3):
                    for metric, bit in METRICS.items():
                        c[f"{arm}_{metric}{k}"] += int(any(f & bit for f in flags[:k]))
        if r["recurrent"]:
            c = per_repo[repo]
            c["n"] += 1
            for k in (1, 3):
                comp = any(f & 2 for f in r["hits"]["compact"][:k])
                for arm, flags in r["hits"].items():
                    other = any(f & 2 for f in flags[:k])
                    c[f"{arm}_hit{k}"] += int(other)
                    c[f"{arm}_plus{k}"] += int(comp and not other)
                    c[f"{arm}_minus{k}"] += int(other and not comp)
    for g in cohort:
        cohort[g]["histories"] = len(cohort_histories[g])
        cohort[g]["repos"] = len(cohort_repos[g])
    assert population["triggers"] == totals["failure_batches"]
    assert cohort["all_labelled"]["n"] == totals["labelled"]
    assert sum(a["n"] for a in per_repo.values()) == cohort["primary"]["n"]
    rng = random.Random(20261116)
    weights = np.zeros((10000, len(repos)), dtype=np.int64)
    for i in range(len(weights)):
        weights[i] = np.bincount(rng.choices(range(len(repos)), k=len(repos)), minlength=len(repos))
    cluster_n = weights @ np.array([per_repo[r]["n"] for r in repos])
    assert np.all(cluster_n > 0)
    pairs = {}
    for arm in ARMS:
        if arm == "compact":
            continue
        for k in (1, 3):
            base = np.array([per_repo[r][f"{arm}_plus{k}"] - per_repo[r][f"{arm}_minus{k}"] for r in repos])
            rates = (weights @ base) / cluster_n
            pairs[f"{arm}@{k}"] = {
                "delta": float(sum(base)/cohort["primary"]["n"]),
                "ci95": np.quantile(rates, [.025,.975]).tolist(),
                "compact_only": sum(c[f"{arm}_plus{k}"] for c in per_repo.values()),
                "other_only": sum(c[f"{arm}_minus{k}"] for c in per_repo.values())}
    with (HERE/"repositories.csv").open("w",newline="",encoding="utf8") as f:
        keys = sorted(set().union(*(x.keys() for x in per_repo.values())))
        w = csv.writer(f)
        w.writerow(["repo",*keys])
        for repo in repos:
            w.writerow([repo,*(per_repo[repo][key] for key in keys)])
    dump("summary.json", {"source_histories":len(index), "source_repos":len(repos),
        "numpy":np.__version__, "totals":dict(totals), "population":dict(population),
        "cohorts":dict(cohort), "stored_text_bytes":dict(stored), "delivered_bytes":dict(delivered),
        "paired_primary":pairs})
    for g, c in cohort.items():
        print(g, c["n"], c["repos"], c["compact_target1"], c["raw_pair_target1"], c["raw_pair_priority_target1"])


if __name__ == "__main__":
    main()
