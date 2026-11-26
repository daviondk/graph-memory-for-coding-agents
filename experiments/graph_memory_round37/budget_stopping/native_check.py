"""Independently check frozen decisions against the authors' span evaluator and raw PU costs."""
from policy import D, WORK, load, np, save, sha
import sys
sys.path.insert(0,str(WORK/"graph_memory_round33/budget_loss"))
import data as bench

def check(stage):
    forecasts = load(D/(stage+"-forecast.json.gz"))
    outcomes = load(D/(stage+"-outcomes.json.gz"))
    refs = load(bench.R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else bench.nm.OFF/"gold-spans.json.gz")
    evaluator = bench.nm.pilot
    seen = set()
    count = 0
    for path in bench.sources(stage):
        for source in load(path):
            q = source["q"]
            assert q not in seen
            seen.add(q)
            f = forecasts[q]
            assert f["t"] == source["t"] == outcomes[q]["t"]
            records = [evaluator.RankedNodeRecord.model_validate(source["rr"][i]) for i in f["order"]]
            spans = tuple(evaluator.SourceSpan.model_validate(v) for v in refs[q])
            prices = [0]+np.cumsum([n.token_count for n in records],dtype=int).tolist()
            assert prices == f["spent"]
            for k in set(f["arms"].values()):
                score = evaluator.span_metrics_under_token_budget(tuple(records[:k]),spans,2048)
                count += 1
                for arm,cut in f["arms"].items():
                    if cut == k:
                        fs,coverage,cost,_,_ = outcomes[q]["arms"][arm]
                        assert cost == prices[k] and abs(fs-score.full_support)<1e-12 and abs(coverage-score.coverage)<1e-12
    assert seen == set(forecasts) == set(outcomes)
    return dict(questions=len(seen),unique_prefixes=count,arm_question_checks=sum(len(x["arms"]) for x in forecasts.values()),
                outcomes=sha(D/(stage+"-outcomes.json.gz")))
if __name__ == "__main__":
    result = {s:check(s) for s in ("dev","test")}
    save("native-audit.json",result)
    print(result)

