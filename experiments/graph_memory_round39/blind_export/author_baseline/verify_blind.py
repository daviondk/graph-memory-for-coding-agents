"""Pure standard-library integrity checks for the unsent SERBench blind submission."""
from panel import *


def main():
    m=read(ROOT/"blind-manifest.json")["files"]
    for path,expected in m.items():
        assert sha(ROOT/path)==expected, path
    seal=read(ROOT/"blind-seal.json")
    assert sha(ROOT/"test500-lexical-residual.jsonl")==seal["blind"]
    assert sha(ROOT/"blind-cal-forecasts.json")==seal["calibration"]
    ranks=[json.loads(s) for s in (ROOT/"test500-lexical-residual.jsonl").read_text(encoding="utf8").splitlines()]
    assert len({r["state_id"] for r in ranks})==len(ranks)==500
    assert sum(len(r["ranked_evidence_ids"])==8 for r in ranks)==seal["coverage"]==491
    assert sum(not r["ranked_evidence_ids"] for r in ranks)==seal["abstained"]==9
    assert seal["validation"]["strict"] and seal["validation"]["valid"] and not seal["validation"]["labels_checked"]
    predictions=read(ROOT/"blind-cal-forecasts.json")
    outcomes=read(ROOT/"blind-outcomes.json")
    scores=read(ROOT/"blind-results.json")
    assert scores["states"]==494 and scores["repos"]==171 and outcomes.keys()==predictions.keys()
    for name,counts in scores["successes"].items():
        assert list(map(sum,zip(*(r["metrics"][name] for r in outcomes.values()))))==counts
    print(f"Verified {len(m)} blind package files, 494 Cal500 forecasts and 500 Test500 rows.")


if __name__=="__main__":
    main()
