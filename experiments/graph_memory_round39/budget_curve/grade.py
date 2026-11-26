"""Grade sealed lists with upstream ISETrace and cross-check disjoint source-span atoms."""
from collections import Counter
from pathlib import Path
from time import perf_counter
import inspect
import sys
from common import D,W,SEEDS,BUDGETS,ORDERS,SELECTORS,read,save,sha,log


def evaluate(seed):
    start = perf_counter()
    pred = D/f"test-{seed}-packets.json.gz"
    seal = D/f"test-{seed}-seal.json"
    assert read(seal)["packets"] == sha(pred)
    dst = D/f"test-{seed}-outcomes.json.gz"
    receipt = D/f"test-{seed}-score-seal.json"
    if receipt.exists():
        assert read(receipt)["outcomes"]==sha(dst)
        log("resume_from_score_seal",seed=seed)
        return
    rows = read(pred)
    sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"))
    import data as upstream
    from graph_memory.evaluation.span_suite import normalized_budget_auc, CONTEXT_TOKEN_BUDGETS
    assert tuple(CONTEXT_TOKEN_BUDGETS)==BUDGETS
    pilot = upstream.nm.pilot
    ref = upstream.nm.OFF/"gold-spans.json.gz"
    truth = read(ref)
    axis_path = W/"graph_memory_round34/interval_witness/test-atoms.json.gz"
    atoms = read(axis_path)
    out, checks = {}, Counter()
    log("score_start",seed=seed)
    for source in upstream.sources("test"):
        for record in read(source):
            q = record["q"]
            t, pack = rows[q]
            assert q not in out and t==record["t"]
            nodes = tuple(pilot.RankedNodeRecord.model_validate(v) for v in record["rr"])
            costs = [n.token_count for n in nodes]
            assert min(costs)>0
            gold = tuple(pilot.SourceSpan.model_validate(g) for g in truth[q])
            spans = [(hi-lo,set(ids)) for _,lo,hi,ids in atoms[q]]
            length = sum(n for n,ix in spans)
            memo, curves = {}, {}
            for i,name in enumerate(ORDERS):
                for j,rule in enumerate(SELECTORS):
                    curve = []
                    for k,b in enumerate(BUDGETS):
                        packet = pack[i][k][j]
                        ix = frozenset(packet)
                        assert len(ix)==len(packet) and all(0<=p<len(nodes) for p in packet)
                        used = sum(costs[p] for p in packet)
                        assert used<=b
                        if ix not in memo:
                            v = pilot.span_metrics_under_token_budget(tuple(nodes[p] for p in packet),gold,b)
                            covered = sum(n for n,s in spans if not ix.isdisjoint(s))
                            assert abs(v.coverage-covered/length)<1e-12 and v.full_support==int(covered==length)
                            memo[ix] = [int(v.full_support),float(v.coverage)]
                        curve.append([*memo[ix],used,len(packet)])
                        checks["budget_and_span_packets"] += 1
                    auc = [normalized_budget_auc(dict(zip(BUDGETS,[row[k] for row in curve]))) for k in (0,1)]
                    curves[name+"/"+rule] = [auc, curve]
                    checks["official_auc_calls"] += 2
            out[q] = [t,curves]
            checks["unique_official_span_calls"] += len(memo)
    assert set(out)==set(rows)
    save(dst,out)
    save(receipt,dict(outcomes=sha(dst),prediction_seal=sha(seal),gold=sha(ref),atoms=sha(axis_path),
        official_spans=sha(Path(inspect.getsourcefile(pilot.span_metrics_under_token_budget))),
        official_auc=sha(Path(inspect.getsourcefile(normalized_budget_auc))),checks=checks,
        records=len(out),code=sha(D/"grade.py")))
    log("score_frozen",seed=seed,seconds=round(perf_counter()-start,3),**checks)
    print("Graded",seed,dict(checks),flush=True)


if __name__=="__main__":
    for s in map(int,sys.argv[1:] or SEEDS):
        evaluate(s)
