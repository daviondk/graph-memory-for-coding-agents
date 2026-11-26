"""Read independent gold only after the 2,000 complete native predictions are sealed."""
from collections import Counter
import os
for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[name] = "1"
import sys
from shared import D, W, C, SEEDS, ARMS, read, sha, save
sys.path.insert(0, str(W / "graph_memory_round33/budget_loss"))
import data as src


def main():
    seal = read(D / "forecast-seal.json")
    file = D / "forecast-packets.json.gz"
    assert sha(file) == seal["predictions"] and seal["questions"] == 2000
    assert sha(C / "forecast-seal.json") == read(D / "registration.json")["causal_forecasts"]
    packets = {q:(t,sets) for q,t,sets in read(file)}
    assert len(packets)==2000
    hybrids={}
    hybrid_receipts={}
    for seed in SEEDS:
        root=D/f"hybrids-{seed}.json.gz"
        receipt=read(D/f"hybrids-{seed}-seal.json")
        assert sha(root)==receipt["data"] and receipt["native"]==sha(D/"forecast-seal.json")
        hybrids[seed]={q:(t,dp,val) for q,t,dp,val in read(root)}
        assert set(hybrids[seed])==set(packets)
        hybrid_receipts[str(seed)]=sha(D/f"hybrids-{seed}-seal.json")
    gold = read(src.nm.OFF / "gold-spans.json.gz")
    intervals = read(W / "graph_memory_round34/interval_witness/test-atoms.json.gz")
    full = []
    cost = Counter()
    for sh, path in enumerate(src.sources("test")):
        prior_file = C / f"outcomes-{sh}.json.gz"
        assert sha(prior_file) == read(C / "scoring.json")["scores"][str(sh)]
        baseline = {r["q"]:r for r in read(prior_file) if r["cut"]==50}
        for item in read(path):
            q,t = item["q"], item["t"]
            tr, arms = packets[q]
            old = baseline[q]
            assert t == tr == old["t"]
            spans = tuple(src.nm.pilot.SourceSpan.model_validate(v) for v in gold[q])
            candidates = tuple(src.nm.pilot.RankedNodeRecord.model_validate(v) for v in item["rr"])
            atoms = [(b-a, set(ids)) for _,a,b,ids in intervals[q]]
            total = sum(w for w,ids in atoms)
            cache = {}
            def score(indices):
                key = tuple(indices)
                if key not in cache:
                    selected = tuple(candidates[i] for i in indices)
                    tokens = sum(n.token_count for n in selected)
                    assert tokens <= 2048 and len(set(indices)) == len(indices)
                    m = src.nm.pilot.span_metrics_under_token_budget(selected,spans,2048)
                    ids = set(indices)
                    mass = sum(w for w,s in atoms if not s.isdisjoint(ids))
                    assert abs(m.coverage-mass/total)<1e-12 and bool(m.full_support)==(mass==total)
                    assert old["eligible"] or not m.full_support
                    cache[key] = [int(m.full_support), float(m.coverage), tokens]
                return cache[key]
            outcomes = {}
            for seed in SEEDS:
                r = dict(old["arms"][str(seed)])
                for arm in ARMS:
                    sets = arms[f"{seed}/{arm}"]
                    for policy, ids in zip(("strict","firstfit","final_restricted_strict","final_restricted_firstfit"),sets,strict=True):
                        r[f"{arm}/{policy}"] = score(ids)
                ht, dp, value = hybrids[seed][q]
                assert ht == t
                r["hybrid_dp"] = score(dp)
                r["hybrid_value"] = score(value)
                outcomes[str(seed)] = r
            full.append(dict(q=q,t=t,pilot=old["pilot"],eligible=old["eligible"],arms=outcomes))
            cost["author_lists_and_interval_checks"] += len(cache)
    assert len(full) == 2000 and len({r["q"] for r in full})==2000
    path = D / "outcomes.json.gz"
    save(path,full)
    save(D / "scoring.json",dict(scores=sha(path),packets=sha(D / "forecast-seal.json"),counts=cost,
        atoms=sha(W / "graph_memory_round34/interval_witness/test-atoms.json.gz"),gold=sha(src.nm.OFF / "gold-spans.json.gz"),
        prior_outcomes=sha(C / "scoring.json"),hybrids=hybrid_receipts,implementation=sha(D / "grade.py")))
    print("graded",len(full),cost,flush=True)


if __name__ == "__main__":
    main()
