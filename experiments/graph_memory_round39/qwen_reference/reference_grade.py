"""Score frozen, complete homogeneous embeddings and matched visibility controls."""
from panel import *
from grade import summarize,score_state,labels
import numpy as np
import sys


def main(mode):
    prefix="gpu-" if mode=="gpu" else ""
    seal=read(ROOT/(prefix+"forecast-seal.json"))
    path=ROOT/(prefix+"qwen-reference.json")
    assert sha(path)==seal["reference"]
    match=read(ROOT/"matched-seal.json")
    assert match["forecasts"]==sha(ROOT/"matched-forecasts.json")
    new=read(path)
    controls=read(ROOT/"matched-forecasts.json")
    rows=read(R34/"features.json.gz")
    assert controls.keys()==new.keys()==read(ROOT/"panel.json")["states"].keys() and len(new)==10
    truth=labels(set(new))
    out={}
    ranks={}
    tok={}
    for q,r in new.items():
        assert len(r["scores"])==len(rows[q]["ids"])
        assert set(r["scores"])==set(rows[q]["ids"])
        rank=controls[q]|r["ranks"]
        values=score_state(rows[q],truth[q],rank)
        out[q]={"repo":rows[q]["repo"],"metrics":values}
        ranks[q]=rank
        lut=dict(zip(rows[q]["ids"],rows[q]["qw"]))
        for name,seq in rank.items():
            tok.setdefault(name,[]).append([sum(lut[x] for x in seq[:k]) for k in (5,8)])
    summary=summarize(out,"R39")
    summary["matched"]={}
    for qwen,ours in (("qwen","r39_no_observed"),("qwen_seen","r39_no_observed_seen"),("qwen_seen","R39")):
        v=summarize(out,ours)["contrasts"][qwen]
        summary["matched"][ours+" minus "+qwen]=v
    summary["timing"]={"states":len(new),"candidate_entries":sum(len(r["scores"]) for r in new.values()),
                       "strings":sum(len(r["lengths"]) for r in new.values()),"truncated":sum(r["truncated"] for r in new.values()),
                       "input_tokens":sum(r["tokens"] for r in new.values()),"seconds":sum(r["seconds"] for r in new.values())}
    rr=summary["timing"]
    rr["wall_tokens_s"]=rr["input_tokens"]/rr["seconds"]
    summary["source_tokens"]={name:np.mean(values,axis=0).tolist() for name,values in tok.items()}
    summary.update(backend=mode,reference_seal=sha(ROOT/(prefix+"forecast-seal.json")),matched_seal=sha(ROOT/"matched-seal.json"))
    write("reference-predictions.json",ranks)
    write("reference-outcomes.json",out)
    write("reference-results.json",summary)
    print(summary["successes"])
    print(summary["timing"])


if __name__=="__main__":
    main(sys.argv[1])
