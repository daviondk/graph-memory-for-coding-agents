"""Export ordinal-only official Cal500 judgments and original unit costs after both ranking runs are fixed."""
from common import *
def main():
    guards=(("gpu-seal.json","qwen-scores.json.gz"),("fusion-seal.json","fusion-predictions.json.gz"))
    for n,f in guards:assert read(OUT/n)["forecasts"]==sha(OUT/f)
    panel=read(OUT/"panel.json");rows=read(R34/"features.json.gz");filtered=set(panel["order"]);d={}
    with gzip.open(PUB/"labels.jsonl.gz","rt",encoding="utf8") as f:
        for label in map(json.loads,f):
            q=label["state_id"]
            if q not in filtered:continue
            r=rows[q];ids=r["ids"];index={v:j for j,v in enumerate(ids)}
            groups=[(g.get("minimum_required",1),g.get("necessity_weight",1.0),[index[e] for e in g["acceptable_evidence_ids"] if e in index]) for g in label["required_evidence_groups"]]
            alts=[[index[e] for e in a] for a in label["alternative_minimal_sets"] if all(e in index for e in a)]
            d[q]=dict(ids=ids,cost=r["qw"],groups=groups,alternative=alts)
    assert set(d)==filtered and len(d)==214
    save("cal-ordinal-judgments.json.gz",d)
    save("audit-seal.json",dict(data=sha(OUT/"cal-ordinal-judgments.json.gz"),cal=sha(PUB/"labels.jsonl.gz"),
         quantities=sha(R34/"features.json.gz"),gpu=sha(OUT/"gpu-seal.json"),fusion=sha(OUT/"fusion-seal.json"),
         code=sha(OUT/"project_checks.py")))
if __name__=="__main__":main()
