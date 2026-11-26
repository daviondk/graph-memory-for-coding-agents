"""Compare frozen three-field and expanded-field policies after verification of token lengths for every GPU input."""
from common import *
from matched_fit import inputs
from grade_panel import score_one,describe,labels,METRICS
def main():
    binding=read(OUT/"matched-seal.json");gpu=read(OUT/"gpu-seal.json");assert binding["forecasts"]==sha(OUT/"matched-predictions.json.gz") and gpu["forecasts"]==sha(OUT/"qwen-scores.json.gz")
    t=inputs();states=t["states"];tok=t["tokens"];qwen=read(OUT/"qwen-scores.json.gz");matched=read(OUT/"matched-predictions.json.gz");panel=read(OUT/"panel.json")
    raw=read(R34/"features.json.gz");official=labels(set(qwen));counts=read(OUT/"controls-seal.json")["observed_counts"];out={};ranked={}
    total=0;differing=[]
    for q in panel["order"]:
        st=states[q];keys=[st["three"],*st["doc"]]
        assert sorted(qwen[q]["scores"])==st["ids"]
        for i,(key,actual) in enumerate(zip(keys,qwen[q]["lengths"],strict=True)):
            if tok[key][0]!=actual:differing.append((q,i,tok[key][0],actual))
        total+=len(keys)
    assert not differing,(len(differing),differing[:4])
    for q in panel["order"]:
        rank=matched[q]|qwen[q]["ranks"];ranked[q]=rank
        metric,cost=score_one(raw[q],official[q],rank)
        out[q]=dict(repo=raw[q]["repo"],arms=metric,tokens=cost,seen=counts[q])
    pairs=[]
    for extension in ("","_seen"):
        for policy in ("bm","lr"):
            pairs.extend(((policy+"three"+extension,"qwen"+extension),(policy+"nine"+extension,policy+"three"+extension)))
    arms=sorted(next(iter(ranked.values())))
    panels={label:describe(ids,out,arms,pairs) for label,ids in (("outside204",panel["remaining"]),("all214",panel["order"]),("pilot10",panel["pilot"]))}
    save("matched-all-ranks.json.gz",ranked);save("matched-outcomes.json.gz",out)
    save("matched-results.json",dict(panels=panels,metrics=METRICS,forecasts=sha(OUT/"matched-seal.json"),backend=sha(OUT/"gpu-seal.json"),
          exact_length_checks=total,length_mismatches=len(differing),held_query_tokenization=sha(OUT/"matched-token-seal.json"),
          outcomes=sha(OUT/"matched-outcomes.json.gz")))
    print("Checked all",total,"Qwen input lengths. Exact-field controls evaluated on 214 states.")
if __name__=="__main__":main()
