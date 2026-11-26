"""Evaluate only the sealed next-document selections, with paired question resampling."""
from collections import Counter
from pathlib import Path
import sys
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"support_pairs"))
from prepare import get,put,sha,PRIVATE
from score import ci_paired

def summarize(rows):
    out={}
    methods=list(rows[0]["exact"])
    for m in methods:
        hit=sum(r["exact"][m] for r in rows)
        seed=sum(r["seed_hit"] for r in rows)
        out[m]={"both":hit,"both_pct":100*hit/len(rows),"doc_recall_pct":50*sum(r["recall"][m] for r in rows)/len(rows),
                "given_correct_seed_pct":100*hit/seed if seed else None}
    contrasts={}
    for a,b in (("mention_local","mention_expanded"),("mention_expanded","expanded"),("mention_expanded","shuffled"),("mention_local","title"),("expanded","title")):
        contrasts[a+"__"+b]=ci_paired([100*(r["exact"][a]-r["exact"][b]) for r in rows])
    pos=[r["first_link"] for r in rows if r["first_link"] is not None]
    return {"n":len(rows),"seed_hits":sum(r["seed_hit"] for r in rows),"methods":out,"contrasts":contrasts,
            "mentions_at_least_one":len(pos),"mentions_multiple":sum(r["mentioned"]>1 for r in rows),
            "link_position_q50_q90":np.quantile(pos,[.5,.9]).tolist() if pos else None,
            "mean_observed_tokens":float(np.mean([r["tokens"] for r in rows])),"max_observed_tokens":max(r["tokens"] for r in rows)}
def main():
    seal=get(HERE/"seal.json");plan=get(HERE/"plan.json")
    assert sha(HERE/"forecasts.json.gz")==seal["forecasts"] and sha(HERE/"plan.json")==seal["plan"]
    src=get(HERE.parent/"support_pairs/source.json");assert all(sha(PRIVATE/(n+".json.gz"))==src[k] for n,k in [("blind","observations"),("labels","labels")])
    cases=get(PRIVATE/"blind.json.gz");truth=get(PRIVATE/"labels.json.gz");pred=get(HERE/"forecasts.json.gz")
    assert set(cases)==set(truth)==set(pred) and {q for q,r in pred.items() if "dense" in r}==set(plan["panel"])
    detailed={}
    for q,row in pred.items():
        titles=[cases[q]["titles"][i] for i in row["catalog"]];g={i for i,t in enumerate(titles) if t in truth[q]["support"]}
        assert len(g)==2;result={}
        for label,arm in row.items():
            if label=="catalog":continue
            seed=arm["seed"];picked=arm["next"];mentions=arm["mentions"]
            assert all(i!=seed and 0<=i<len(titles) for i in picked.values()) and 0<=arm["tokens"]<=192
            count={m:len(g&{seed,i}) for m,i in picked.items()}
            result[label]={"seed_hit":int(seed in g),"recall":count,"exact":{m:int(v==2) for m,v in count.items()},
                           "mentioned":len(mentions),"first_link":min((min(p) for p in mentions.values()),default=None),"tokens":arm["tokens"]}
        detailed[q]=result
    panels={"sparse":[r["sparse"] for r in detailed.values()],
            "sparse_512":[detailed[q]["sparse"] for q in plan["panel"]],"dense_512":[detailed[q]["dense"] for q in plan["panel"]]}
    summary={p:summarize(rows) for p,rows in panels.items()}
    active={p:summarize([r for r in rows if r["mentioned"]>1]) for p,rows in panels.items() if any(r["mentioned"]>1 for r in rows)}
    paired_seed={m:ci_paired([100*(detailed[q]["dense"]["exact"][m]-detailed[q]["sparse"]["exact"][m]) for q in plan["panel"]]) for m in panels["sparse"][0]["exact"]}
    put(HERE/"outcomes.json.gz",detailed);put(HERE/"results.json",{"panels":summary,"multiple_links_exploratory":active,"dense_minus_sparse_512":paired_seed,"outcomes":sha(HERE/"outcomes.json.gz")})
if __name__=="__main__":main()
