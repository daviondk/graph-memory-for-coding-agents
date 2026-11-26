"""Fit each model on other repositories and seal every allocation before grading."""
import hashlib
import os
import sys

os.environ["OPENBLAS_NUM_THREADS"] = "1"
import numpy as np

from inputs import HERE, R54, TASKS, digest, read, save

sys.path.insert(0, str(R54 / "learned_read"))
from evaluate import fit, sigmoid

MODELS = ("static", "snapshot", "history")
ORDER_SEEDS = range(55001, 55033)


def discount(rank):
    return 0.0 if rank == 0 else 1.0 / np.log2(1 + rank)


def build_matrix(projection, obs):
    rows, groups, masses, slices = [], [], [], {}
    for q, item in sorted(projection.items()):
        t = obs[q]
        current = t["proposals"][-1]
        past = [{p: i for i, p in enumerate(seq, 1)} for seq in t["proposals"][:-1]]
        start = len(rows)
        for path, rank in zip(item["paths"], item["ranks"], strict=True):
            assert (rank[7] > 0) == (path in current)
            base = [1.0] + [discount(r) for r in rank[:7]] + [int(t["task"] == tp) for tp in TASKS]
            snapshot = [discount(rank[7])] + [n / (1 + n) for n in t["counts"]]
            pre = [prior[path] for prior in past if path in prior]
            history = [len(pre) / max(1, len(past)), discount(min(pre, default=0)),
                       int(bool(pre) and path not in current), int(bool(pre) and path in current)]
            rows.append(base + snapshot + history)
            groups.append(t["repo"])
            masses.append(1.0 / len(item["paths"]))
        slices[q] = slice(start, len(rows))
    matrix = np.array(rows)
    assert matrix.shape[1] == 22
    return dict(static=matrix[:, :11], snapshot=matrix[:, :18], history=matrix), np.array(groups), np.array(masses), slices


def best_two(scores):
    return sorted(range(len(scores)), key=lambda i: -scores[i])[:2]


def allocate(ranked, score):
    choices = {q: [] for q in ranked}
    pairs = [(score[q][i], q, i) for q, seq in ranked.items() for i in seq]
    for _, q, i in sorted(pairs, key=lambda t: (-t[0], t[1], t[2]))[:len(ranked)]:
        choices[q].append(i)
    assert sum(map(len, choices.values())) == len(ranked)
    return choices


def online(ranked, score, train_values, seed):
    choices = {}
    order = sorted(ranked, key=lambda q: hashlib.sha256(f"{seed}/{q}".encode()).digest())
    remaining = len(order)
    budget = remaining
    for q in order:
        quantile = 1 - budget / (2 * remaining)
        threshold = float(np.quantile(train_values, quantile, method="linear"))
        count = sum(score[q][i] >= threshold for i in ranked[q])
        count = min(budget, max(budget - 2 * (remaining - 1), count))
        choices[q] = ranked[q][:count]
        budget -= count
        remaining -= 1
    assert budget == 0 and sum(map(len, choices.values())) == len(ranked)
    return choices


def main():
    reg = read(HERE / "registration.json")
    assert reg["model"] == digest(HERE / "predict.py")
    assert reg["protocol"] == digest(HERE / "PROTOCOL_RU.md") and reg["fit"] == digest(R54 / "learned_read/evaluate.py")
    assert reg["projection"] == digest(R54 / "learned_read/projection.json.gz")
    assert reg["observations"] == digest(HERE / "observations.json.gz")
    projection = read(R54 / "learned_read/projection.json.gz")
    obs = read(HERE / "observations.json.gz")
    labels = read(R54 / "next_read/labels.json.gz")
    mats, groups, weight, spans = build_matrix(projection, obs)
    folds, decisions, scores, sequential = {}, {}, {}, {}
    for repo in sorted(set(groups)):
        train_ids = [q for q in sorted(obs) if obs[q]["repo"] != repo]
        test_ids = [q for q in sorted(obs) if obs[q]["repo"] == repo]
        train_mask = groups != repo
        target = np.array([float(p in labels[q]) for q in train_ids for p in projection[q]["paths"]])
        assert len(target) == train_mask.sum() and np.isclose(weight[train_mask].sum(), len(train_ids))
        assert not set(train_ids) & set(test_ids)
        folds[repo] = dict(train_ids=train_ids, test_ids=test_ids, models={})
        banks = {}
        for model in MODELS:
            matrix = mats[model]
            beta, info = fit(matrix[train_mask], target, weight[train_mask])
            folds[repo]["models"][model] = info
            pred = sigmoid(matrix @ beta)
            train_top = np.sort(np.concatenate([np.sort(pred[spans[q]])[-2:] for q in train_ids]))
            score = {q: pred[spans[q]].tolist() for q in test_ids}
            banks[model] = score
            ranked = {q: best_two(score[q]) for q in test_ids}
            assert all(len(pair) == 2 for pair in ranked.values())
            for seed in ORDER_SEEDS:
                allocation = online(ranked, score, train_top, seed)
                sequential.setdefault(str(seed), {}).setdefault(model, {}).update(allocation)
        for q in test_ids:
            row = projection[q]
            rrf = [sum(1 / (60 + r) for r in col[:7] if r) for col in row["ranks"]]
            banks.setdefault("rrf7", {})[q] = rrf
            dense = [r[0] if r[0] else 1_000_000 for r in row["ranks"]]
            fi = int(np.argmin(dense))
            fallback = dense[fi] == 1_000_000
            if fallback:
                fi = best_two(rrf)[0]
            decisions[q] = {"embed4_fixed": [fi]}
            scores[q] = dict(dense_fallback=bool(fallback))
        for name, score in banks.items():
            ranked = {q: best_two(score[q]) for q in test_ids}
            chosen = allocate(ranked, score)
            for q in test_ids:
                decisions[q][name + "_fixed"] = ranked[q][:1]
                decisions[q][name + "_batch"] = chosen[q]
                scores[q][name] = score[q]
                if name in MODELS:
                    decisions[q][name + "_online"] = sequential["55001"][name][q]
    save("oof-scores.json.gz", scores)
    save("oof-models.json.gz", folds)
    save("decisions.json.gz", decisions)
    save("sequential-orders.json.gz", sequential)
    files = ["registration.json", "oof-scores.json.gz", "oof-models.json.gz", "decisions.json.gz", "sequential-orders.json.gz"]
    save("prediction-seal.json", {name: digest(HERE / name) for name in files})


if __name__ == "__main__":
    main()
