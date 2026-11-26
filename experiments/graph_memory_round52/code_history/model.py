"""Streaming prefix-only ranker, conditional logit fitting, and frozen test predictions."""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from prepare_data import HERE, read, save, sha

BASE = ["inverse_age", "inverse_recency_rank", "view_count_saturated", "edit_count_saturated",
        "last_touch_was_read", "same_directory"]
EDGE = ["forward_switches", "reverse_switches", "edit_to_next_view"]

def sat(n):
    return n / (n + 1)

def targets(trace):
    """Associate a grade with a pending edit. Only invoked on train when fitting."""
    future, assignments, clear = None, {}, True
    for at, kind, path in reversed(trace["events"]):
        if kind == "E":
            assignments[at] = (future, clear)
            future, clear = None, True
        elif kind == "R":
            future, clear = path, True
        elif kind == "B":
            clear = False
    return assignments

def stream(trace):
    last = {}
    reads, edits = Counter(), Counter()
    last_kind, incoming, outgoing = {}, {}, {}
    counts, typed = Counter(), Counter()
    prev = pending = None
    step = 0
    history = sha256()
    for at, kind, path in trace["events"]:
        history.update(kind.encode())
        if kind == "B":
            continue
        history.update(bytes.fromhex(trace["paths_sha256"][path]))
        step += 1
        if prev is not None and prev != path:
            counts[prev, path] += 1
            incoming[path], outgoing[prev] = prev, path
        prev = path
        if kind == "R":
            if pending is not None and pending != path:
                typed[pending, path] += 1
            pending = None
            reads[path] += 1
        else:
            assert kind == "E"
            pending = path
            edits[path] += 1
        last[path], last_kind[path] = step, kind
        if kind != "E":
            continue
        candidates = sorted((other for other in last if other != path), key=lambda i: -last[i])
        base, edge, sham = [], [], []
        for rank, other in enumerate(candidates, 1):
            base.append([1 / (1 + step - last[other]), 1 / rank, sat(reads[other]), sat(edits[other]),
                         int(last_kind[other] == "R"), int(trace["directory"][other] == trace["directory"][path])])
            for result, source in ((edge, path), (sham, candidates[0])):
                result.append([sat(counts[source, other]), sat(counts[other, source]), sat(typed[source, other])])
        recent = candidates[0] if candidates else None
        controls = {"mru": recent,
                    "lfu": max(candidates, key=lambda o: reads[o] + edits[o], default=None),
                    "incoming": incoming.get(path, recent), "outgoing": outgoing.get(path, recent)}
        yield {"at": at, "path": path, "pool": candidates, "base": base, "edge": edge, "sham": sham,
               "controls": controls, "switch_edges": len(counts), "typed_edges": len(typed),
               "prefix": history.hexdigest()}

def fit(samples, edge=False, weights_base=None):
    dims = len(EDGE if edge else BASE)
    if not samples:
        raise RuntimeError("No identifiable conditional choices")
    sizes = Counter(s[0] for s in samples)
    weights = np.array([1 / (len(sizes) * sizes[s[0]]) for s in samples])
    data = [(np.asarray(row["edge" if edge else "base"], dtype=float),
             np.asarray(row["base"], dtype=float) @ weights_base if edge else np.zeros(len(row["pool"])))
            for _, row, _ in samples]
    def objective(v):
        loss, grad = .005 * (v @ v), .01 * v.copy()
        for (_, _, gold), (x, offset), weight in zip(samples, data, weights):
            score = x @ v + offset
            denom = logsumexp(score)
            loss += weight * (denom - score[gold])
            grad += weight * (np.exp(score - denom) @ x - x[gold])
        return loss, grad
    result = minimize(objective, np.zeros(dims), jac=True, method="L-BFGS-B", options={"gtol": 1.e-9, "ftol": 1.e-13})
    assert result.success, result.message
    return result.x, {"loss": result.fun, "gradient_max": max(abs(result.jac))}

def train():
    rows, signatures, stats = [], set(), Counter()
    runs = read(HERE / "train_trace.json.gz")
    for trace in runs:
        gold = targets(trace)
        for row in stream(trace):
            stats["edits"] += 1
            dest, _ = gold[row["at"]]
            if dest is None:
                continue
            stats["has_next_view"] += 1
            if len(row["pool"]) < 2 or dest not in row["pool"]:
                continue
            stats["reachable_discriminating_before_dedup"] += 1
            sig = (trace["issue"], row["prefix"], trace["paths_sha256"][dest])
            if sig in signatures:
                continue
            signatures.add(sig)
            rows.append((trace["issue"], row, row["pool"].index(dest)))
    beta, log1 = fit(rows)
    gamma, log2 = fit(rows, True, beta)
    save("model.json", {"beta": beta.tolist(), "gamma": gamma.tolist(), "features": BASE + EDGE,
                        "l2": .01, "solver": [log1, log2], "training": dict(stats),
                        "identifiable_unique": len(rows), "fit_issues": dict(Counter(r[0] for r in rows)),
                        "all_train_repos": sorted({r["repo"] for r in runs}),
                        "protocol_sha256": sha(HERE / "PROTOCOL_RU.md"), "code_sha256": sha(Path(__file__)),
                        "train_sha256": sha(HERE / "train_trace.json.gz")})
    print("fit complete", len(rows), len({r[0] for r in rows}), dict(stats))

def forecast():
    model = read(HERE / "model.json")
    assert sha(HERE / "PROTOCOL_RU.md") == model["protocol_sha256"] and sha(Path(__file__)) == model["code_sha256"]
    forecasts = []
    for trace in read(HERE / "test_trace.json.gz"):
        for row in stream(trace):
            pool = row["pool"]
            pred = row["controls"].copy()
            for policy, key in (("baseline", None), ("graph", "edge"), ("sham", "sham")):
                if pool:
                    score = np.asarray(row["base"]) @ model["beta"]
                    if key:
                        score += np.asarray(row[key]) @ model["gamma"]
                    pred[policy] = pool[int(np.argmax(score))]
                else:
                    pred[policy] = None
            assert all(choice is None or choice in pool for choice in pred.values())
            forecasts.append({"issue": trace["issue"], "repo": trace["repo"], "panel": trace["panel"],
                              **{k:row[k] for k in ("at","path","pool","switch_edges","typed_edges","prefix")},
                              "supported": any(any(feats) for feats in row["edge"]), "pred": pred})
    save("forecasts.json.gz", forecasts)
    save("forecast_seal.json", {n: sha(HERE / n) for n in ("PROTOCOL_RU.md", "model.py", "model.json",
                                                           "test_trace.json.gz", "forecasts.json.gz")})
    print("sealed forecasts", len(forecasts))

if __name__ == "__main__":
    {"fit": train, "forecast": forecast}[sys.argv[1]]()

