"""Check the out-of-fold fit, decoded ranks and allocation, using separate arithmetic."""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import numpy as np

from inputs import HERE, R54, TASKS, digest, read, save
from grade import evaluate
from byte_grade import grade

def main():
    evaluate(True)
    grade(True)
    projected = read(R54 / "learned_read/projection.json.gz")
    obs = read(HERE/"observations.json.gz")
    labels = read(R54/"next_read/labels.json.gz")
    decisions = read(HERE/"decisions.json.gz")
    p = read(HERE/"oof-scores.json.gz")
    folds = read(HERE/"oof-models.json.gz")
    original = read(R54/"next_read/explicit-decisions.json.gz")
    first = read(R54/"next_read/fusion-choices.json.gz")
    features, slices, groups, masses, target = [], {}, [], [], []
    for q,row in sorted(projected.items()):
        start = len(features)
        t = obs[q]
        frac = lambda x: x / (x + 1)
        val = lambda r: 0 if r == 0 else 1 / np.log2(r + 1)
        for file, rr in zip(row["paths"],row["ranks"]):
            membership = [seq.index(file)+1 if file in seq else 0 for seq in t["proposals"]]
            surviving = membership[-1] > 0
            assert rr[-1] == membership[-1]
            old = [k for k in membership[:-1] if k]
            features.append([1, *map(val,rr[:7]), *[int(t["task"]==k) for k in TASKS],
                             val(rr[-1]), *map(frac,t["counts"]), len(old)/max(1,len(membership)-1),
                             max(map(val,old),default=0), bool(old) and not surviving, bool(old) and surviving])
            groups.append(t["repo"])
            masses.append(1/len(row["paths"]))
            target.append(int(file in labels[q]))
        slices[q] = slice(start,len(features))
        assert row["paths"][decisions[q]["embed4_fixed"][0]] == original[q]["chosen"]["embed4"]
        assert row["paths"][decisions[q]["rrf7_fixed"][0]] == first[q]["chosen"]["static_seven"]
    x = np.asarray(features)
    g = np.asarray(groups)
    y = np.asarray(target)
    w = np.asarray(masses)
    max_gradient = 0.
    max_prob_error = 0.
    queries = 0
    for name,fold in folds.items():
        train = g != name
        test = set(fold["test_ids"])
        assert test == {q for q in projected if obs[q]["repo"] == name}
        assert set(fold["train_ids"]) == set(projected)-test
        for m, width in (("static",11),("snapshot",18),("history",22)):
            beta = np.array(fold["models"][m]["weights"])
            prob = 1/(1+np.exp(-(x[:,:width]@beta)))
            grad = x[train,:width].T@(w[train]*(prob[train]-y[train]))
            grad[1:] += beta[1:]
            max_gradient = max(max_gradient,float(np.max(np.abs(grad))))
            for q in test:
                max_prob_error=max(max_prob_error,float(np.max(np.abs(prob[slices[q]]-p[q][m]))))
            pool = []
            for q in test:
                seq = sorted(range(len(p[q][m])),key=lambda j:(-p[q][m][j],j))[:2]
                pool.extend((q,j) for j in seq)
            expected = sorted(pool,key=lambda x:(-p[x[0]][m][x[1]], x[0], x[1]))[:len(test)]
            actual = {(q,j) for q in test for j in decisions[q][m+"_batch"]}
            assert set(expected) == actual
            queries += len(test)
    assert max_gradient < 1e-8 and max_prob_error < 1e-12
    save("audit.json",dict(folds=len(folds), trained_models=3*len(folds),
         candidate_pairs=len(groups), verified_oof_probabilities=3*len(groups), checked_batch_decisions=queries,
         matched_individual_dense_and_rrf=len(projected)*2, max_gradient=max_gradient, max_probability_error=max_prob_error,
         solver_groups_checked=len(folds), byte_allocations_checked=9*len(projected),
         terminal_log_disagreements=sum(t["terminal_augmented"] for t in obs.values()),
         primary_results_verified=True, byte_results_verified=True))


if __name__=="__main__":
    main()
