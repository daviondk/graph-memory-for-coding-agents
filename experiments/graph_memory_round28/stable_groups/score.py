"""Evaluate sealed grouping predictions and the work needed after one update."""
from collections import defaultdict
import importlib.util
from pathlib import Path
import sys
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"revoked_evidence"))
from capture import P,read,save,sha
from prepare import RAW

def paired(table,left,right,field,seed):
    groups=defaultdict(list)
    for row in table.values():
        groups[row["article"]].append(row[left][field]-row[right][field])
    article_means=np.array([np.mean(group) for _,group in sorted(groups.items())])
    rng=np.random.default_rng(seed)
    means=article_means[rng.integers(len(article_means),size=(20000,len(article_means)))].mean(axis=1)
    return {"difference":float(np.mean(article_means)),"ci95":np.quantile(means,[.025,.975]).tolist(),
            "higher":sum(r[left][field]>r[right][field] for r in table.values()),
            "lower":sum(r[left][field]<r[right][field] for r in table.values())}

def main():
    lock=read(HERE/"forecast-lock.json")
    assert sha(HERE/"forecasts.json.gz")==lock["forecasts"]
    cases=read(HERE/"forecasts.json.gz");blind=read(P/"blind-input.json.gz")
    labels={q["id"]:[v["text"] for v in q["answers"]] for a in read(RAW)["data"] for p in a["paragraphs"] for q in p["qas"]}
    assert len(cases)==96 and all(q in labels for q in cases)
    sp=importlib.util.spec_from_file_location("official_squad",P/"official.py")
    official=importlib.util.module_from_spec(sp);sp.loader.exec_module(official)
    states=("base","random","winner","append");modes=("stream","single","repack3","stable3","anchors")
    outcomes={s:{} for s in states}
    for q,case in cases.items():
        base=case["read"]["base"];article=case["title"]
        for state,table in outcomes.items():
            row={"article":article,"random_is_winner":case["random_is_winner"]}
            for mode in modes:
                existing={t for t,n in base[mode]["windows"]} if state!="base" else set()
                view=case["read"][state][mode]
                windows=view["windows"];unique=dict(windows)
                new=[n for t,n in unique.items() if t not in existing]
                a=view["answer"];address=a[1:] if a else None
                surface=blind["docs"][article][slice(*address)] if address else ""
                refs=labels[q]
                f1,em=[100*official.metric_max_over_ground_truths(fn,surface,refs)
                       for fn in (official.f1_score,official.exact_match_score)]
                row[mode]={"groups":view["groups"],"windows":len(windows),"tokens":sum(n for _,n in windows),
                           "fresh":len(new),"fresh_tokens":sum(new),"f1":f1,"em":em,"address":address}
            assert state!="base" or row["stable3"]==row["repack3"]
            def surface(mode):
                address=row[mode]["address"]
                return blind["docs"][article][slice(*address)] if address else ""
            row["same_surface"]=surface("stable3")==surface("repack3")
            table[q]=row
    results={}
    for state,table in outcomes.items():
        cols=["groups","windows","tokens","fresh","fresh_tokens","f1","em"]
        results[state]={"means":{m:{k:float(np.mean([v[m][k] for v in table.values()])) for k in cols} for m in modes},
                        "stable3_minus_repack3":{k:paired(table,"stable3","repack3",k,28161) for k in ("fresh","fresh_tokens","f1","em")},
                        "same_address":sum(v["stable3"]["address"]==v["repack3"]["address"] for v in table.values()),
                        "same_surface":sum(v["same_surface"] for v in table.values())}
    save(HERE/"outcomes.json.gz",outcomes)
    save(HERE/"results.json",{"n":len(cases),"article_count":len({r["title"] for r in cases.values()}),
         "random_equals_winner":sum(r["random_is_winner"] for r in cases.values()),
         "onnx_unique":sum(r["unique_calls"] for r in cases.values()),"independent_forwards":sum(r["fresh_audit_calls"] for r in cases.values()),
         "states":results,"forecasts":lock["forecasts"],"outcomes":sha(HERE/"outcomes.json.gz")})
if __name__=="__main__":main()
