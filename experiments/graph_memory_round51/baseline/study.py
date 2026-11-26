"""CPU-only matched ranking controls using frozen round 50 panel material."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import binomtest

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "graph_memory_round50"
PANELS = ["semantic_address", "adaptive_address", "gate_confirmation"]
HOLDOUT = PANELS[1:]
FEATURES = ["cosine", "reciprocal_question_rank", "reciprocal_snippet_rank",
            "reciprocal_dense_rank", "visible_mention"]
CUTOFF = 0.04178261756896973
DATAFILES = ["orders.json.gz", "contexts.json.gz", "gold.json.gz", "outcomes.json.gz",
             "answers.json.gz", "prompts.json.gz", "catalog-receipts.json.gz"]


def raw(path):
    content = path.read_bytes()
    return json.loads(gzip.decompress(content) if path.suffix == ".gz" else content)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    path = HERE / name
    content = (json.dumps(data, sort_keys=True, indent=None if name.endswith(".gz") else 2,
                          allow_nan=False) + "\n").encode()
    path.write_bytes(gzip.compress(content, compresslevel=9, mtime=0)
                     if name.endswith(".gz") else content)


def lex_file(panel):
    if panel == PANELS[0]:
        return SOURCE / "qa_replication" / "orders.json.gz"
    return SOURCE / panel / "lex-orders.json.gz"


def register():
    paths = {SOURCE / p / f for p in PANELS for f in DATAFILES}
    paths.update(lex_file(p) for p in PANELS)
    provenance = {}
    for path in sorted(paths):
        sha = digest(path)
        assert raw(path.parent / "manifest.json")["files"][path.name] == sha
        provenance[path.relative_to(SOURCE).as_posix()] = sha
    save("registration.json", {"files": provenance, "protocol": digest(HERE / "PROTOCOL_RU.md"),
                               "source_stage": "archived R50, all aggregate baselines previously public"})


def features(rank, lex):
    ids = rank["order"]
    assert len(ids) == len(set(ids)) == 9 and rank["seed"] == lex["seed"]
    assert ids[0] == rank["dense"] and set(rank["edges"]) == set(map(int, lex["edges"]))
    return np.array([[rank["scores"][str(i)], 1 / (1 + lex["question_rank"][str(i)]),
                      1 / (1 + lex["snippet_rank"][str(i)]), 1 / (1 + j),
                      float(i in rank["edges"])] for j, i in enumerate(ids)])


def panel_data(panel):
    path = SOURCE / panel
    ranks = raw(path / "orders.json.gz")
    lexical = raw(lex_file(panel))
    return ranks, {qid: features(rank, lexical[qid]) for qid, rank in ranks.items()}


def fit_rank(xs, gold, ranks, dim):
    pairs = []
    weights = []
    for q in sorted(xs):
        _, titles, support = gold[q]
        positive = np.array([titles[i] in support for i in ranks[q]["order"]])
        differences = (xs[q][positive, None, :dim] - xs[q][None, ~positive, :dim]).reshape(-1, dim)
        if len(differences):
            pairs.extend(differences)
            weights.extend([1 / len(differences)] * len(differences))
    x, w = np.asarray(pairs), np.asarray(weights)
    n = len(xs)

    def fun(b):
        z = x @ b
        loss = w @ np.logaddexp(0, -z) + .5 * np.dot(b, b)
        gradient = -(w * expit(-z)) @ x + b
        return loss / n, gradient / n

    opt = minimize(fun, np.zeros(dim), jac=True, method="L-BFGS-B",
                   options={"ftol": 1e-15, "gtol": 1e-10, "maxiter": 1000})
    assert opt.success and np.max(np.abs(opt.jac)) < 1e-6
    return {"coef": opt.x.tolist(), "pairs": len(pairs), "effective_queries": round(w.sum()),
            "loss": opt.fun, "gradient_max": float(abs(opt.jac).max())}


def fit():
    ranks, x = panel_data(PANELS[0])
    train = SOURCE / PANELS[0]
    gold = raw(train / "gold.json.gz")
    outcomes = raw(train / "outcomes.json.gz")
    allx = np.vstack([x[q] for q in sorted(x)])
    mean, scale = allx.mean(axis=0), allx.std(axis=0)
    scale[scale == 0] = 1
    std = {q: (v - mean) / scale for q, v in x.items()}
    model = {"registration": digest(HERE / "registration.json"), "features": FEATURES,
             "mean": mean.tolist(), "scale": scale.tolist(),
             "hybrid": fit_rank(std, gold, ranks, 4), "graph": fit_rank(std, gold, ranks, 5)}
    diffs, targets = [], []
    for q in sorted(ranks):
        a, b = ranks[q]["dense"], ranks[q]["linked_dense"]
        if a == b:
            continue
        order = ranks[q]["order"]
        diffs.append((std[q][order.index(b)] - std[q][0])[:4])
        arms = outcomes[q]["arms"]
        targets.append(arms["linked_dense"][1] - arms["dense"][1])
    x, y = np.asarray(diffs), np.array(targets)
    xc, yc = x - x.mean(axis=0), y - y.mean()
    beta = np.linalg.solve(xc.T @ xc + 10 * np.eye(x.shape[1]), xc.T @ yc)
    model["answer_gain"] = {"coef": beta.tolist(), "intercept": y.mean() - x.mean(axis=0) @ beta,
                            "n": len(y), "positive": int((y > 0).sum()), "negative": int((y < 0).sum())}
    save("model.json", model)


def select():
    m = raw(HERE / "model.json")
    predictions = {}
    train_ids = set(panel_data(PANELS[0])[0])
    seen = set(train_ids)
    clusters = set()
    for p in PANELS:
        ctx = raw(SOURCE / p / "contexts.json.gz")
        keys = [v["cluster"] for v in ctx.values()]
        assert len(set(keys)) == len(keys) and not clusters.intersection(keys)
        clusters.update(keys)
    for p in HOLDOUT:
        ranks, x = panel_data(p)
        assert not seen.intersection(ranks)
        seen.update(ranks)
        selected = {}
        for q in sorted(x):
            r = ranks[q]
            ids = r["order"]
            dense, linked = r["dense"], r["linked_dense"]
            j = ids.index(linked)
            gap = r["scores"][str(dense)] - r["scores"][str(linked)]
            gate = linked if gap <= CUTOFF else dense
            assert gate == r["adaptive"]
            std = (x[q] - m["mean"]) / m["scale"]
            choices = {"dense": dense, "linked": linked, "gate": gate}
            for name in ("hybrid", "graph"):
                coef = m[name]["coef"]
                scores = std[:, :len(coef)] @ coef
                choices[name] = ids[int(np.argmax(scores))]
                choices[name + "_pair"] = linked if scores[j] > scores[0] else dense
            gain = (std[j, :4] - std[0, :4]) @ m["answer_gain"]["coef"] + m["answer_gain"]["intercept"]
            choices["answer_pair"] = linked if gain > 0 else dense
            selected[q] = choices
        predictions[p] = selected
    save("decisions.json.gz", predictions)
    save("decision-seal.json", {"registration": digest(HERE / "registration.json"),
                                "model": digest(HERE / "model.json"), "code": digest(Path(__file__)),
                                "decisions": digest(HERE / "decisions.json.gz")})


def ci_records(values, rng, n_boot=10000):
    n, cols = values.shape
    boot = np.empty((n_boot, cols))
    for start in range(0, n_boot, 100):
        rows = rng.integers(0, n, size=(min(100, n_boot-start), n))
        boot[start:start+len(rows)] = values[rows].mean(axis=1)
    bounds = np.quantile(boot, [.025, .975], axis=0)
    return [[float(values[:, j].mean()*100), float(bounds[0,j]*100), float(bounds[1,j]*100)]
            for j in range(cols)]


def evaluate():
    choices = raw(HERE / "decisions.json.gz")
    assert digest(HERE / "decisions.json.gz") == raw(HERE / "decision-seal.json")["decisions"]
    result, evidence = {}, {}
    strategy_names = list(next(iter(choices[HOLDOUT[0]].values())).keys())
    for p in HOLDOUT:
        base = SOURCE / p
        ctx, outcomes, gold = [raw(base / x) for x in ("contexts.json.gz", "outcomes.json.gz", "gold.json.gz")]
        rows = {}
        for q, decisions in choices[p].items():
            refs = ctx[q]["refs"]
            known = {}
            for arm, (target, prompt, tokens) in refs.items():
                record = [prompt, *outcomes[q]["arms"][arm][:2]]
                assert known.setdefault(target,record) == record
            first = ctx[q]["seed"]
            _, titles, support = gold[q]
            facts = set(support)
            row = {}
            for mode, i in decisions.items():
                found = {titles[first], titles[i]}
                matched = len(facts & found)
                rec = known.get(i)
                row[mode] = {"choice": i, "full": int(matched == len(facts)), "recall": matched/len(facts),
                             "em": rec[1] if rec else None, "f1": rec[2] if rec else None,
                             "prompt": rec[0] if rec else None}
            rows[q] = row
        evidence[p] = rows
        metric = {}
        for name in strategy_names:
            vals = [rows[q][name] for q in sorted(rows)]
            fs = [v["f1"] for v in vals if v["f1"] is not None]
            es = [v["em"] for v in vals if v["em"] is not None]
            n = len(vals)
            metric[name] = {"n": n, "full_support": sum(v["full"] for v in vals)/n,
                            "support_recall": sum(v["recall"] for v in vals)/n,
                            "covered": len(fs), "unknown": n-len(fs), "known_f1_sum": math.fsum(fs),
                            "known_em_sum": sum(es), "f1_range": [math.fsum(fs)/n,(math.fsum(fs)+n-len(fs))/n],
                            "switches": sum(row[name]["choice"] != row["dense"]["choice"] for row in rows.values())}
        pairs = [("graph", "gate"), ("graph", "hybrid"), ("hybrid", "dense"), ("graph", "linked"),
                 ("graph_pair","gate"), ("graph_pair","hybrid_pair"),("graph_pair","linked"),
                 ("answer_pair","gate"),("answer_pair","linked")]
        keys, data = [], []
        for a,b in pairs:
            for metric_name in ("full","recall","f1","em"):
                if metric_name in ("f1","em") and (metric[a]["unknown"] or metric[b]["unknown"]):
                    continue
                keys.append((a,b,metric_name))
                data.append([rows[q][a][metric_name] - rows[q][b][metric_name] for q in sorted(rows)])
        mat = np.asarray(data).T
        intervals = ci_records(mat, np.random.default_rng(510271))
        contrasts = {}
        for i, ((a,b,k), (est,lo,hi)) in enumerate(zip(keys, intervals)):
            vals = mat[:,i]
            pos, neg = int((vals>1e-12).sum()), int((vals< -1e-12).sum())
            entry = {"delta_pp": est, "ci95_pp": [lo,hi], "gains":pos, "losses":neg}
            if a=="graph" and b=="gate" and k=="full":
                entry["mcnemar_exact_two_sided"] = float(binomtest(pos,pos+neg,.5).pvalue) if pos+neg else 1.0
            contrasts.setdefault(a+"-"+b,{})[k] = entry
        result[p] = {"policies": metric, "contrasts": contrasts}
    save("records.json.gz", evidence)
    save("results.json", result)


if __name__ == "__main__":
    actions = {"register":register, "fit":fit, "select":select, "grade":evaluate}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=actions)
    stage = parser.parse_args().stage
    if stage != "register":
        lock = raw(HERE / "registration.json")
        assert lock["protocol"] == digest(HERE / "PROTOCOL_RU.md")
        assert all(digest(SOURCE / p) == h for p,h in lock["files"].items())
    actions[stage]()
    print(stage, "OK")
