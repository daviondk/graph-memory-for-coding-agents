"""Evaluate an additional fusion contrast only after its own ranking seal."""
from common import *
from grade_panel import score_one, describe, labels, METRICS


def main():
    binding=read(OUT/"fusion-seal.json")
    assert sha(OUT/"fusion-predictions.json.gz")==binding["forecasts"]
    pred=read(OUT/"fusion-predictions.json.gz");raw=read(R34/"features.json.gz");panel=read(OUT/"panel.json")
    gold=labels(set(pred));seen=read(OUT/"controls-seal.json")["observed_counts"]
    assert len(pred)==214
    out={}
    for q in panel["order"]:
        metrics,cost=score_one(raw[q],gold[q],pred[q])
        out[q]=dict(repo=raw[q]["repo"],seen=seen[q],arms=metrics,tokens=cost)
    arms=sorted(next(iter(pred.values())))
    pairs=[("r39_seen","qwen_seen"),("r39","qwen"),("r39_seen","bge_seen"),
           ("r39_seen","union_seen"),("r39","bge"),("r39","union")]
    tabs={name:describe(ids,out,arms,pairs) for name,ids in
          (("outside204",panel["remaining"]),("all214",panel["order"]),("pilot10",panel["pilot"]))}
    save("fusion-outcomes.json.gz",out)
    save("fusion-results.json",dict(metrics=METRICS,panels=tabs,seal=sha(OUT/"fusion-seal.json"),outcomes=sha(OUT/"fusion-outcomes.json.gz")))
    print({k:r["complete_counts"] for k,r in tabs["outside204"]["methods"].items()})


if __name__=="__main__":main()
