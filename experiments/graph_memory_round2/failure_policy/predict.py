"""Leave one project out. The predictor receives no held-out labels or task identifiers as features."""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import math
import numpy as np

ROOT = Path(__file__).resolve().parent
ARMS = ["HISTORY", "NONE", "SIGNAL", "REFLECT", "BOTH"]


def values(row):
    return set(row["x"].items())


def best(scores):
    highest = max(scores)
    return ARMS[next(i for i, score in enumerate(scores) if highest-score <= 1e-12)]


def predict(train, test, training_labels, held_project):
    assert {r["id"] for r in test}.isdisjoint(training_labels)
    assert {r["project"] for r in train}.isdisjoint({held_project})
    assert len({r["project"] for r in test}) == 1
    y = np.array([[training_labels[r["id"]][a] for a in ARMS] for r in train], dtype=float)
    clean = y - y.mean(axis=1, keepdims=True)
    counts = Counter(r["task"] for r in train)
    w = np.array([1.0/counts[r["task"]] for r in train])
    prior = np.average(clean, weights=w, axis=0)
    tokens = [values(r) for r in train]
    vocab = sorted(set.union(*tokens))
    df = Counter(t for row in tokens for t in row)
    idf = {t: 1.0 + math.log((1 + len(tokens))/(1 + df[t])) for t in vocab}
    new_idf = 1.0 + math.log(1 + len(tokens))
    def encode(s):
        return np.array([float(t in s) for t in vocab])
    x_train = np.stack([encode(s) for s in tokens])
    mean_x = np.average(x_train, weights=w, axis=0)
    xc = x_train - mean_x
    coef = np.linalg.solve(xc.T @ (xc*w[:, None]) + 4*np.eye(len(vocab)),
                           xc.T @ ((clean-prior)*w[:, None]))
    placebo = clean.copy()
    groups = defaultdict(list)
    for i, row in enumerate(train):
        groups[row["project"]].append(i)
    for group in groups.values():
        order = sorted(group, key=lambda i: hashlib.sha256(("r2d-placebo|"+held_project+"|"+train[i]["id"]).encode()).hexdigest())
        placebo[order] = clean[np.roll(order, 1)]
    placebo_prior = np.average(placebo, weights=w, axis=0)
    pred = {}
    for row in test:
        q = values(row)
        kernel = np.array([(sum(idf.get(t, new_idf) for t in sorted(q & tset)) /
                            sum(idf.get(t, new_idf) for t in sorted(q | tset)))**3 for tset in tokens])
        weights = w*kernel
        def graph(a, base):
            return best((4.0*base + weights @ a)/(4.0 + weights.sum()))
        pred[row["id"]] = {"graph": graph(clean, prior), "placebo": graph(placebo, placebo_prior),
                           "constant_cv": best(prior), "ridge": best(prior + (encode(q)-mean_x) @ coef)}
    return pred


def main():
    rows = json.loads((ROOT/"features.json").read_text(encoding="utf-8"))
    labels = json.loads((ROOT/"labels.json").read_text(encoding="utf-8"))
    all_predictions = {}
    for project in sorted({r["project"] for r in rows}):
        train = [r for r in rows if r["project"] != project]
        test = [r for r in rows if r["project"] == project]
        training_labels = {r["id"]: labels[r["id"]] for r in train}
        all_predictions.update(predict(train, test, training_labels, project))
    assert set(all_predictions) == set(labels)
    (ROOT/"predictions.json").write_text(json.dumps(all_predictions, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    print(f"{len(all_predictions)} cross-project predictions")


if __name__ == "__main__":
    main()
