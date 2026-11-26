"""Grade sealed OOF files against official relevance with repository-level pairing."""
import argparse
from collections import Counter

import numpy as np

from inputs import HERE, R54, digest, read, save

METRICS = ("hits_per_100_reads", "new_hit_episodes_pct", "total_recall_pct", "complete_pct")
CONTRASTS = (
    ("history_batch", "snapshot_batch"), ("history_batch", "history_fixed"),
    ("history_batch", "static_batch"), ("snapshot_batch", "static_batch"),
    ("history_batch", "rrf7_batch"), ("history_batch", "embed4_fixed"),
    ("history_online", "snapshot_online"), ("history_online", "static_online"),
    ("history_online", "history_batch"), ("history_fixed", "snapshot_fixed"),
    ("static_batch", "static_fixed"),
)


def evaluate(verify):
    seal = read(HERE / "prediction-seal.json")
    assert all(digest(HERE / n) == h for n, h in seal.items())
    assert read(HERE / "registration.json")["evaluator"] == digest(HERE / "grade.py")
    data = read(R54 / "learned_read/projection.json.gz")
    obs = read(HERE / "observations.json.gz")
    labels = {q: set(x) for q, x in read(R54 / "next_read/labels.json.gz").items()}
    decisions = read(HERE / "decisions.json.gz")
    alternate = read(HERE / "sequential-orders.json.gz")
    oof = read(HERE / "oof-scores.json.gz")
    folds = read(HERE / "oof-models.json.gz")
    ids = sorted(decisions)
    repos, ix = np.unique([obs[q]["repo"] for q in ids], return_inverse=True)
    size = np.bincount(ix)
    assert set(ids) == set(data) == set(obs) == set(labels)
    alternatives = sorted(decisions[ids[0]])
    samples = {m: [] for m in alternatives}
    ledger = {}
    counts = Counter()
    outcome_upper = {}
    for q in ids:
        item, trace, gold = data[q], obs[q], labels[q]
        past = set(item["strict"])
        assert gold and q not in folds[trace["repo"]]["train_ids"] and q in folds[trace["repo"]]["test_ids"]
        assert set(item["paths"]).isdisjoint(past)
        prev = {p for seq in trace["proposals"][:-1] for p in seq}
        last = set(trace["proposals"][-1])
        counts["episodes_previous_final"] += int(len(trace["proposals"]) > 1)
        counts["withdrawn_pairs"] += len(prev - last)
        counts["reinforced_pairs"] += len(prev & last)
        counts["episodes_withdrawn"] += bool(prev - last)
        counts["episodes_reinforced"] += bool(prev & last)
        counts["dense_fallback"] += oof[q]["dense_fallback"]
        counts["episodes_strict_complete"] += gold.issubset(past)
        ranked_gold = [k for k, p in enumerate(item["paths"]) if p in gold]
        outcome_upper[q] = min(2, len(ranked_gold))
        ledger[q] = {}
        for model in alternatives:
            choice = decisions[q][model]
            assert len(choice) <= 2 and len(set(choice)) == len(choice) and all(0 <= i < len(item["paths"]) for i in choice)
            new = {item["paths"][j] for j in choice}
            hits = len(new & gold)
            covered = len((past | new) & gold)
            metrics = [hits, int(hits > 0), covered / len(gold), int(covered == len(gold))]
            ledger[q][model] = dict(reads=len(new), hits=hits, covered=covered, relevant=len(gold))
            samples[model].append(metrics)
    results = dict(n=len(ids), repos=len(repos), distinct_queries=len({t["query_hash"] for t in obs.values()}),
                   distinct_snapshots=len({(t["repo"],t["commit"]) for t in obs.values()}),
                   distinct_snapshot_queries=len({(t["repo"],t["commit"],t["query_hash"]) for t in obs.values()}),
                   diagnostics=dict(counts), metrics_order=list(METRICS), methods={}, contrasts={}, by_repo={})
    matrix = {}
    oracle = 0
    for g in repos:
        group_ids = [q for q in ids if obs[q]["repo"] == g]
        oracle += min(len(group_ids), sum(outcome_upper[q] for q in group_ids))
        groupsums = {}
        for m in alternatives:
            groupcost = sum(ledger[q][m]["reads"] for q in group_ids)
            assert groupcost == len(group_ids)
            groupsums[m] = sum(ledger[q][m]["hits"] for q in group_ids)
        results["by_repo"][g] = dict(episodes=len(group_ids), hits=groupsums)
    results["oracle_batch_hits"] = oracle
    results["oracle_fixed_hits"] = sum(v > 0 for v in outcome_upper.values())
    rng = np.random.default_rng(55001)
    draws = rng.integers(len(repos), size=(10000, len(repos)))
    for name, s in samples.items():
        v = matrix[name] = np.asarray(s)
        allocation = Counter(ledger[q][name]["reads"] for q in ids)
        results["methods"][name] = dict(hits=int(v[:,0].sum()), hit_episodes=int(v[:,1].sum()),
                                         rates=dict(zip(METRICS, (100*v.mean(axis=0)).tolist())),
                                         allocations=[allocation[k] for k in range(3)])
    for left, right in CONTRASTS:
        change = matrix[left] - matrix[right]
        cluster_sums = np.zeros((len(repos), len(METRICS)))
        np.add.at(cluster_sums, ix, change)
        boot = 100*cluster_sums[draws].sum(axis=1)/size[draws].sum(axis=1)[:,None]
        ci = np.quantile(boot,[.025,.975],axis=0)
        result = {"delta_pp": (100*change.mean(0)).tolist(), "ci95_pp": ci.T.tolist(),
                  "macro_repo_pp": (100*(cluster_sums/size[:,None]).mean(0)).tolist(),
                  "repo_win_tie_loss": [int((cluster_sums[:,0] > 0).sum()), int((cluster_sums[:,0] == 0).sum()),
                                        int((cluster_sums[:,0] < 0).sum())],
                  "episode_win_tie_loss": [int((change[:,0] > 0).sum()), int((change[:,0] == 0).sum()),
                                           int((change[:,0] < 0).sum())]}
        results["contrasts"][f"{left}-{right}"] = result
    distribution = {}
    for seed, models in sorted(alternate.items()):
        for m, policy in models.items():
            assert set(policy) == set(ids)
            for g in repos:
                chunk = [q for q in ids if obs[q]["repo"] == g]
                assert sum(len(policy[q]) for q in chunk) == len(chunk)
            hits = sum(sum(data[q]["paths"][i] in labels[q] for i in values) for q, values in policy.items())
            distribution.setdefault(m, {})[seed] = hits
    results["order_sensitivity_hits"] = distribution
    for fname, value in [("results.json", results), ("episode-outcomes.json.gz", ledger)]:
        if verify:
            assert read(HERE / fname) == value
        else:
            save(fname, value)
    print("files found:", {k: v["hits"] for k,v in results["methods"].items()})
    print("history minus snapshot:", results["contrasts"]["history_batch-snapshot_batch"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    evaluate(parser.parse_args().verify)
