"""Independent checks on raw feature ranks, trained parameters, probabilities, selected addresses and endpoints."""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import numpy as np
from features import D, SRC, read, sha, put

ARMS = ("memory8", "static7", "static8", "rrf7", "rrf3")
MODELS = ARMS[:3]


def main():
    reg = read(D / "registration.json")
    seal = read(D / "prediction-seal.json")
    for root, file, expected in [
        (D, "registration.json", seal["registration"]), (D, "features.py", reg["builder"]),
        (D, "evaluate.py", seal["model"]), (D, "PROTOCOL_RU.md", reg["protocol"]),
        (SRC, "labels.json.gz", seal["labels"]), (D, "projection.json.gz", seal["projection"]),
        (D, "oof-decisions.json.gz", seal["decisions"]), (D, "oof-models.json.gz", seal["parameters"]),
        (D, "oof-probabilities.json.gz", seal["probabilities"])
    ]:
        assert sha(root / file) == expected, file
    raw = read(SRC / "fusion-inputs.json.gz")
    facts = read(SRC / "explicit-decisions.json.gz")
    frozen = read(SRC / "fusion-choices.json.gz")
    gold = {q: set(paths) for q, paths in read(SRC / "labels.json.gz").items()}
    features = read(D / "projection.json.gz")
    decisions = read(D / "oof-decisions.json.gz")
    fits = read(D / "oof-models.json.gz")
    probabilities = read(D / "oof-probabilities.json.gz")
    report = read(D / "results.json")
    matrices, truth = {}, {}
    for q, record in raw.items():
        paths = record["lexical_order"]
        assert paths == features[q]["paths"]
        assert set(paths).isdisjoint(facts[q]["opened"])
        assert set(paths).isdisjoint(features[q]["strict"])
        sources = [record["ranks"][key] for key in reg["members"]] + [facts[q]["new_suggestions"]]
        orders = np.array([[s.index(p) + 1 if p in s else 0 for s in sources] for p in paths])
        assert orders.tolist() == features[q]["ranks"]
        values = np.zeros_like(orders, dtype=float)
        found = orders > 0
        values[found] = 1 / np.log2(orders[found] + 1)
        matrices[q] = {}
        for m in MODELS:
            eighth = {"memory8": values[:, -1], "static8": found[:, :7].mean(1),
                      "static7": np.zeros(len(paths))}[m]
            matrices[q][m] = np.column_stack((np.ones(len(paths)), values[:, :7], eighth))
        truth[q] = np.asarray([p in gold[q] for p in paths], dtype=float)
    max_gradient = 0.
    max_probability_error = 0.
    comparisons = 0
    all_episodes = {}
    members = {q: fact["repo"] for q, fact in facts.items()}
    for panel, fold_map in fits.items():
        within = {q for q,g in members.items() if panel == "all" or g != report["diagnostics"]["largest"]}
        assert set(decisions[panel]) == within
        scored = {}
        for g, fold in fold_map.items():
            train, test = set(fold["train_ids"]), set(fold["test_ids"])
            assert train == {q for q in within if members[q] != g}
            assert test == within - train and set(fold["train_groups"]) == {members[q] for q in train}
            for m in MODELS:
                beta = np.asarray(fold["models"][m]["weights"])
                grad = beta.copy()
                grad[0] = 0.
                for q in sorted(train):
                    x = matrices[q][m]
                    p = 1 / (1 + np.exp(-(x @ beta)))
                    grad += x.T @ (p - truth[q]) / len(x)
                error = float(max(abs(grad)))
                assert error < 1e-7, (panel, g, m, error)
                max_gradient = max(max_gradient, error)
                for q in test:
                    logits = matrices[q][m] @ beta
                    p = 1 / (1 + np.exp(-logits))
                    other = probabilities[panel][q][m]
                    max_probability_error = max(max_probability_error, float(max(abs(p - other))))
                    assert np.allclose(p, other, rtol=2e-13, atol=1e-15)
                    assert decisions[panel][q][m] == features[q]["paths"][np.argmax(logits)]
                    comparisons += len(other)
        for q in sorted(within):
            paths = features[q]["paths"]
            known = set(facts[q]["strict"]) & gold[q]
            arms = {}
            for m in ARMS:
                p = decisions[panel][q][m]
                i = paths.index(p)
                hit = int(p in gold[q])
                if m.startswith("rrf"):
                    assert p == frozen[q]["chosen"]["static_seven" if m == "rrf7" else "triple"]
                arms[m] = dict(path=p, new_hit=hit, total_recall=(len(known)+hit)/len(gold[q]),
                               static_ranks=features[q]["ranks"][i][:7],
                               verified_proposal_rank=features[q]["ranks"][i][-1])
                if m in MODELS:
                    arms[m]["score"] = probabilities[panel][q][m][i]
            scored[q] = dict(repo=members[q], candidates=len(paths), gold=len(gold[q]), strict_gold=len(known),
                             proposals=len(facts[q]["new_suggestions"]), arms=arms)
        for m in ARMS:
            vals = [x["arms"][m] for x in scored.values()]
            expected = report[panel]["summary"][m]
            assert sum(a["new_hit"] for a in vals) == expected["new_hits"]
            assert np.isclose(100*np.mean([a["total_recall"] for a in vals]), expected["total_recall_pct"])
        for label, expected in report[panel]["contrasts"].items():
            a,b = label.split(" vs ")
            for field in ("new_hit", "total_recall"):
                diffs = [v["arms"][a][field] - v["arms"][b][field] for v in scored.values()]
                assert np.isclose(100*np.mean(diffs), expected[field]["delta_pp"])
                assert sum(x > 0 for x in diffs) == expected[field]["wins"]
                assert sum(x < 0 for x in diffs) == expected[field]["losses"]
        all_episodes[panel] = scored
    put("per-episode.json.gz", all_episodes)
    receipt = dict(status="PASS",folds=len(fits["all"])+len(fits["without_largest"]),
                   newton_fits=3*(len(fits["all"])+len(fits["without_largest"])),
                   max_training_only_gradient=max_gradient, max_probability_error=max_probability_error,
                   oof_probabilities_compared=comparisons, independently_scored_cases={p:len(v) for p,v in all_episodes.items()},
                   per_episode_sha256=sha(D / "per-episode.json.gz"), results_sha256=sha(D / "results.json"))
    put("audit.json", receipt)
    print(receipt)


if __name__ == "__main__":
    main()

