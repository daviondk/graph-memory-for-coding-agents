"""Optimize a capped source-read queue without opening any evaluation labels."""
import scipy
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from inputs import HERE, digest, read, save

MODELS = ("static","snapshot","history","rrf7")
SCALE = 1_000_000_000


def solve(weights, price, occurrence, cap, count):
    n = len(price)
    variables = np.ones(n)
    bounds = Bounds(np.zeros(n), variables)
    clauses = [LinearConstraint(variables, count, count),
               LinearConstraint(occurrence, np.zeros(count), np.full(count, 2))]
    if cap is not None:
        clauses.append(LinearConstraint(price, -np.inf, cap))

    def optimize(target):
        result = milp(c=target, constraints=clauses, integrality=variables,
                      bounds=bounds, options={"mip_rel_gap": 0.0})
        if result.status != 0:
            raise RuntimeError(f"HiGHS terminated: {result.message}")
        nearest = np.rint(result.x).astype(np.int64)
        assert np.max(np.abs(nearest - result.x)) < 1e-5
        assert nearest.sum() == count and np.max(occurrence @ nearest) <= 2
        assert cap is None or price @ nearest <= cap
        return nearest, result
    best, primary = optimize(-weights)
    achieved = int(weights @ best)
    clauses.append(LinearConstraint(weights, achieved, achieved))
    first, tie = optimize(price)
    assert weights @ first == achieved
    return first, dict(utility_integer=achieved, returned_bytes=int(price @ first),
                       primary_mip_gap=float(primary.mip_gap), tie_mip_gap=float(tie.mip_gap),
                       primary_dual=float(primary.mip_dual_bound), tie_dual=float(tie.mip_dual_bound))


def main():
    reg = read(HERE / "byte-registration.json")
    assert reg["costs"] == digest(HERE / "first-chunks.json.gz") and reg["optimizer"] == digest(HERE / "byte_budget.py")
    assert reg["protocol"] == digest(HERE / "BYTE_PROTOCOL_RU.md") and reg["predictions"] == digest(HERE / "prediction-seal.json")
    observed = read(HERE / "observations.json.gz")
    score = read(HERE / "oof-scores.json.gz")
    chunks = read(HERE / "first-chunks.json.gz")
    prior = read(HERE / "decisions.json.gz")
    choices = {q: {"dense": prior[q]["embed4_fixed"]} for q in observed}
    certificates = {}
    for repo in sorted({o["repo"] for o in observed.values()}):
        ids = sorted(q for q in observed if observed[q]["repo"] == repo)
        candidates = [(q, i) for q in ids for i in sorted(map(int, chunks[q]))]
        price = np.array([chunks[q][str(i)][1] for q,i in candidates], dtype=np.int64)
        membership = np.array([[q == group for q,i in candidates] for group in ids], dtype=float)
        budget = sum(chunks[q][str(choices[q]["dense"][0])][1] for q in ids)
        checks = certificates[repo] = {"byte_cap": budget, "episodes": len(ids), "options": len(candidates)}
        for name in MODELS:
            weights = np.rint(SCALE*np.array([score[q][name][i] for q,i in candidates])).astype(np.int64)
            for prefix, cap in [("count_", None), ("bytes_", budget)]:
                code = prefix + name
                selected, details = solve(weights, price, membership, cap, len(ids))
                checks[code] = details
                for q in ids:
                    choices[q][code] = []
                for (q,i), flag in zip(candidates, selected):
                    if flag:
                        choices[q][code].append(i)
    save("byte-decisions.json.gz", choices)
    save("solver-certificates.json", dict(scipy=scipy.__version__, scale=SCALE, groups=certificates))
    save("byte-seal.json", {n: digest(HERE/n) for n in ("byte-registration.json","byte-decisions.json.gz","solver-certificates.json")})


if __name__ == "__main__":
    main()
