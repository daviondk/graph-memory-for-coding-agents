"""Verify all ten Qwen results without access to the GPU or the SERBench labels."""
from panel import *
import math


def verify():
    m=read(ROOT/"qwen-manifest.json")["files"]
    for path,expected in m.items():
        assert sha(ROOT/path)==expected,path
    seal=read(ROOT/"gpu-forecast-seal.json")
    forecasts=read(ROOT/"gpu-qwen-reference.json")
    assert sha(ROOT/"gpu-qwen-reference.json")==seal["reference"]
    assert sha(ROOT/"seal_gpu.py")==seal["seal_program"]
    for name,digest in seal["inputs"].items():
        if name not in ("model","runtime"):
            assert sha(ROOT/name)==digest
    panel=read(ROOT/"panel.json")["states"]
    ranks=read(ROOT/"reference-predictions.json")
    outcomes=read(ROOT/"reference-outcomes.json")
    summary=read(ROOT/"reference-results.json")
    controls=read(ROOT/"matched-forecasts.json")
    matched=read(ROOT/"matched-seal.json")
    assert sha(ROOT/"matched.py")==matched["code"] and sha(ROOT/"matched-forecasts.json")==matched["forecasts"]
    assert sha(ROOT/"gpu-forecast-seal.json")==summary["reference_seal"] and summary["backend"]=="gpu"
    assert sha(ROOT/"matched-seal.json")==summary["matched_seal"]
    assert forecasts.keys()==ranks.keys()==outcomes.keys()==panel.keys()==controls.keys() and len(panel)==10
    assert len({v["repo"] for v in panel.values()})==10
    for q,raw in forecasts.items():
        scores=raw["scores"]
        assert len(scores)==panel[q]["candidates"] and all(math.isfinite(x) and abs(x)<=1.0001 for x in scores.values())
        assert len(raw["lengths"])==len(scores)+1 and all(x>0 for x in raw["lengths"])
        assert raw["tokens"]==sum(min(n,512) for n in raw["lengths"])
        assert raw["truncated"]==sum(n>512 for n in raw["lengths"])
        assert raw["ranks"]["qwen"]==sorted(scores,key=lambda k:(-scores[k],k))[:8]
        assert ranks[q]==controls[q]|raw["ranks"]
        assert all(len(set(s))==len(s)==8 for s in ranks[q].values())
    assert summary["timing"]["candidate_entries"]==sum(len(v["scores"]) for v in forecasts.values())==952
    assert summary["timing"]["input_tokens"]==sum(r["tokens"] for r in forecasts.values())==377486
    assert summary["timing"]["truncated"]==sum(r["truncated"] for r in forecasts.values())==474
    for key,total in summary["successes"].items():
        assert list(map(sum,zip(*(r["metrics"][key] for r in outcomes.values()))))==total
    print(f"Verified {len(m)} files, 10 held-out repositories, 952 raw candidate scores and 9 matched-policy alternatives.")


if __name__=="__main__":
    verify()
