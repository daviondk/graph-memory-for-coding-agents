"""Decompose final answer differences by preexisting and newly extractable evidence."""
from collections import defaultdict
import gzip
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()))
def compute():
    d=ROOT/"directional_answers"
    scores=read(d/"per-query.json.gz")
    forecasts=read(d/"predictions.json.gz")
    out={}
    for control in ("adaptive","right"):
        strata=defaultdict(list)
        for q,r in scores.items():
            a,b,base=(r["arms"][k] for k in ("both",control,"base"))
            pa,pb=(forecasts[q]["arms"][k] for k in ("both",control))
            x,y=a["extractable_fragment"],b["extractable_fragment"]
            tag=("base" if base["extractable_fragment"] else "new_common") if x and y else ("both_only" if x else "control_only" if y else "neither")
            v=a["f1"]-b["f1"]
            strata[tag].append((v,a["em"]-b["em"],int(pa["answer_sha"]!=pb["answer_sha"]),a["correct_address"]-b["correct_address"]))
        out[control]={name:{"n":len(items),"wins":sum(it[0]>0 for it in items),"losses":sum(it[0]<0 for it in items),
                           "f1_pp_of_total":100*sum(it[0] for it in items)/len(scores),
                           "net_em":sum(it[1] for it in items),"answer_text_changed":sum(it[2] for it in items),
                           "net_exact_address":sum(it[3] for it in items)} for name,items in sorted(strata.items())}
    return out
if __name__=="__main__":
    data=compute()
    (ROOT/"answer-attribution.json").write_text(json.dumps(data,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(json.dumps(data))

