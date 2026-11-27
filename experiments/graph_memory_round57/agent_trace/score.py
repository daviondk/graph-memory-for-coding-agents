"""Score frozen forecasts, bootstrapping paired issues with both actors kept together."""
from collections import Counter, defaultdict
from statistics import fmean
import numpy as np

from extract import HERE, digest, read, save
from replay import METHODS


def bootstrap(rows):
    if not rows:
        return None
    issues = sorted(set(r[0] for r in rows))
    idx = {k: i for i, k in enumerate(issues)}
    totals = np.zeros((len(issues), 2))
    for group, numerator, denominator in rows:
        totals[idx[group]] += (numerator, denominator)
    weights = np.random.default_rng(57083).multinomial(len(issues), [1 / len(issues)] * len(issues), size=20000)
    a, b = (weights @ totals).T
    return {"delta": float(totals[:, 0].sum() / totals[:, 1].sum()),
            "ci": np.quantile(a[b > 0] / b[b > 0], [.025, .975]).tolist(),
            "issues": len(issues), "macro_issue": float(np.mean(totals[:, 0] / totals[:, 1]))}


def score(sample, drop_current):
    if not sample:
        return {"n": 0}
    costs = Counter()
    output = {}
    for method in METHODS:
        for t, row in sample:
            order = [p for p in row["ranks"][method] if not drop_current or p != row["current"]]
            pos = order.index(row["target"]) + 1 if row["target"] in order else 0
            key = (t["issue"], t["actor"], row["at"])
            output.setdefault(key, {})[method] = [int(pos == 1), int(0 < pos <= 3), 1 / pos if pos else 0]
    for _, r in sample:
        costs["own"] += r["cost"][0]
        costs["shared"] += r["cost"][1]
        costs["full"] += r["cost"][2]
        costs["activated"] += bool(r["shared_extra_indices"])
    comparisons = {}
    for control in ("own", "lru", "frequency", "name", "directed", "full"):
        details = [(q, v["shared"][0] - v[control][0], 1) for (q, actor, time), v in output.items()]
        comparisons["shared__" + control] = {
            **bootstrap(details), "wins": sum(z[1] > 0 for z in details), "losses": sum(z[1] < 0 for z in details)}
    return {"n": len(sample), "traces": len({(r["issue"], r["actor"]) for r, _ in sample}),
            "tasks": len({r["issue"] for r, _ in sample}), "repos": len({r["repo"] for r, _ in sample}),
            "decoded": dict(costs), "means": {m: [fmean(v[m][j] for v in output.values()) for j in range(3)] for m in METHODS},
            "comparisons": comparisons}


def cache_score(records, only_open=True):
    pairs = [(t, row) for t in records for row in t["cache"] if not only_open or row["action"] == "open"]
    total = sum(r["size"] for t, r in pairs)
    out = {"n": len(pairs), "requested_bytes": total}
    for m in ("graph", "lru"):
        served = sum(r["served"][m][0] for t, r in pairs)
        out[m] = {"served": served, "fraction": served / total,
                  "complete": sum(r["served"][m][1] for t, r in pairs),
                  "conflicting_lines": sum(r["served"][m][2] for t, r in pairs), "peak": max(t["peak"][m] for t in records)}
    out["paired_byte_fraction"] = bootstrap([(t["issue"], r["served"]["graph"][0] - r["served"]["lru"][0], r["size"]) for t, r in pairs])
    return out


def main():
    for n, hash_ in read(HERE / "forecast-seal.json").items():
        assert digest(HERE / n) == hash_
    traces = read(HERE / "forecasts.json.gz")
    pool = [(t, r) for t in traces for r in t["predictions"]]
    switches = [(t, r) for t, r in pool if r["current"] != r["target"]]
    primary = [(t, r) for t, r in switches if r["target"] in r["ranks"]["lru"]]
    actors = {t["actor"] for t in traces}
    results = {"scope": {"traces": len(traces), "tasks": len({t["issue"] for t in traces}),
                          "repos": len({t["repo"] for t in traces}), "raw_actions": sum(len(t["events"]) for t in read(HERE / "prefixes.json.gz")),
                          "barriers": sum(t["barriers"] for t in traces)},
               "primary": score(primary, True), "all_open_after_any_view": score(pool, False),
               "all_switches": score(switches, True),
               "intervening": score([(t, r) for t, r in primary if r["at"] - r["previous_at"] > 1], True),
               "actors": {a: score([(t, r) for t, r in primary if t["actor"] == a], True) for a in sorted(actors)},
               "cache_open": cache_score(traces), "cache_all_views": cache_score(traces, False)}
    save(HERE / "results.json", results)
    for k in ("primary", "all_open_after_any_view", "all_switches", "intervening"):
        r = results[k]
        print(k, r["n"], r["tasks"], r["decoded"], {m: round(r["means"][m][0], 4) for m in METHODS}, r["comparisons"]["shared__own"])
    print(results["cache_open"])
    print(results["scope"])


if __name__ == "__main__":
    main()
