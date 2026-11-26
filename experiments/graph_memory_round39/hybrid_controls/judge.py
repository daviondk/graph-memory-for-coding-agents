"""Separate official evaluator. Every seed must have a frozen forecast before opening spans."""
from collections import Counter
import inspect
from pathlib import Path
import sys
from time import perf_counter
from shared import D,W,CURVE,SEEDS,BUDGETS,ORDERS,RULES,read,sha,save,log


def measure(seed):
    start=perf_counter()
    assert all((D/f"test-{s}-seal.json").is_file() for s in SEEDS)
    dst=D/f"test-{seed}-outcomes.json.gz"
    receipt=D/f"test-{seed}-score-seal.json"
    if receipt.exists():
        assert sha(dst)==read(receipt)["outcomes"]
        return
    src=D/f"test-{seed}-packets.json.gz"
    assert sha(src)==read(D/f"test-{seed}-seal.json")["packets"]
    pred=read(src)
    sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"))
    import data as upstream
    from graph_memory.evaluation.span_suite import normalized_budget_auc, CONTEXT_TOKEN_BUDGETS
    assert tuple(CONTEXT_TOKEN_BUDGETS)==BUDGETS
    gold_path=upstream.nm.OFF/"gold-spans.json.gz"
    atom_path=W/"graph_memory_round34/interval_witness/test-atoms.json.gz"
    truth,atoms=read(gold_path),read(atom_path)
    pilot=upstream.nm.pilot
    ref=read(CURVE/f"test-{seed}-outcomes.json.gz")
    tallies=Counter()
    out={}
    for shard in upstream.sources("test"):
        for raw in read(shard):
            q=raw["q"]
            t,rows=pred[q]
            assert raw["t"]==t==ref[q][0]
            nodes=[pilot.RankedNodeRecord.model_validate(n) for n in raw["rr"]]
            gold=tuple(pilot.SourceSpan.model_validate(s) for s in truth[q])
            axis=[(hi-lo,set(ids)) for _,lo,hi,ids in atoms[q]]
            length=sum(n for n,_ in axis)
            memo,metrics={},{}
            for o,order in enumerate(ORDERS):
                for m,rule in enumerate(RULES):
                    name=order+"/"+rule
                    curve=[]
                    for i,b in enumerate(BUDGETS):
                        ids=rows[o][i][m]
                        ix=frozenset(ids)
                        assert len(ix)==len(ids) and all(0<=j<len(nodes) for j in ix)
                        seq=tuple(nodes[j] for j in ids)
                        cost=sum(n.token_count for n in seq)
                        assert cost<=b
                        if ix not in memo:
                            v=pilot.span_metrics_under_token_budget(seq,gold,b)
                            covered=sum(n for n,indices in axis if not indices.isdisjoint(ix))
                            assert abs(v.coverage-covered/length)<1e-12 and v.full_support==int(covered==length)
                            memo[ix]=[int(v.full_support),float(v.coverage)]
                        curve.append([*memo[ix],cost,len(seq)])
                    areas=[normalized_budget_auc(dict(zip(BUDGETS,(v[j] for v in curve)))) for j in (0,1)]
                    metrics[name]=[areas,curve]
                    if rule in ("strict","firstfit","graph_dp"):
                        assert metrics[name]==ref[q][1][name]
                        tallies["curve_arm_budget_matches"]+=len(BUDGETS)
                a=metrics[order+"/graph_density"][1]
                b=metrics[order+"/graph_dp_equal_spend"][1]
                assert all(v[2]==w[2] for v,w in zip(a,b))
                tallies["exact_token_matches"]+=len(BUDGETS)
            tallies["span_calls"]+=len(memo)
            out[q]=[t,metrics]
    assert set(out)==set(pred)
    tallies["all_packets"]=len(out)*len(BUDGETS)*len(ORDERS)*len(RULES)
    save(dst,out)
    save(receipt,dict(seed=seed,counters=tallies,outcomes=sha(dst),prediction_seal=sha(D/f"test-{seed}-seal.json"),
        scorer=sha(Path(inspect.getsourcefile(pilot.span_metrics_under_token_budget))),gold=sha(gold_path),atoms=sha(atom_path),
        official_auc=sha(Path(inspect.getsourcefile(normalized_budget_auc))),judge=sha(D/"judge.py")))
    log("graded",seed=seed,seconds=round(perf_counter()-start,3),**tallies)
    print("scored",seed,dict(tallies),flush=True)


if __name__=="__main__":
    for seed in map(int,sys.argv[1:] or SEEDS):
        measure(seed)
