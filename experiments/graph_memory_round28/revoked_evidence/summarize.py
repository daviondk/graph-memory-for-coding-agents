"""Join benchmark labels only after the post-retraction forecasts are sealed."""
from collections import defaultdict
import importlib.util
from statistics import fmean,median
import numpy as np
from capture import HERE,PREVIOUS,P,read,save,sha

def aggregate(rows):
    return {"n":len(rows),"mean":fmean(rows),"median":median(rows),"min":min(rows),"max":max(rows)}

def main():
    seal=read(HERE/"decision-seal.json");assert seal["decisions"]==sha(HERE/"decisions.json.gz")
    data=read(HERE/"decisions.json.gz");states=read(HERE/"state-forecasts.json.gz")
    view=read(P/"blind-input.json.gz")
    raw=read(PREVIOUS.parents[0]/"directional_answers"/"input-lock.json")
    from prepare import RAW
    assert sha(RAW)==raw["source"]
    labels={}
    for a in read(RAW)["data"]:
        sourcepos=0
        for para in a["paragraphs"]:
            for question in para["qas"]:
                q=question["id"]
                if q in data:
                    labels[q]=[(r["text"],sourcepos+r["answer_start"],sourcepos+r["answer_start"]+len(r["text"])) for r in question["answers"]
                        if para["context"][r["answer_start"]:r["answer_start"]+len(r["text"])]==r["text"]]
            sourcepos+=len(para["context"])+2
    assert all(labels[q] for q in data)
    sp=importlib.util.spec_from_file_location("official_squad",P/"official.py");off=importlib.util.module_from_spec(sp);sp.loader.exec_module(off)
    qa={}
    for q,r in data.items():
        variants={**r["answers"],"old_with_mask":r["projections"]["record"]["answer"]}
        answers={}
        for mode,v in variants.items():
            src=view["docs"][r["article"]];text=src[v[2]:v[3]] if v is not None else ""
            answers[mode]=[off.metric_max_over_ground_truths(metric,text,[x[0] for x in labels[q]])
                           for metric in (off.f1_score,off.exact_match_score)]
        covered=any(l<=gl<gh<=h for l,h,_ in states[q]["states"]["retract"]["parts"] for _,gl,gh in labels[q])
        qa[q]={"article":r["article"],"answers":answers,"gold_in_residual":covered}
    costs={}
    for mode in ("append","retract"):
        fields=["windows","exact_cache","logit_cache","prefix_cache","measured_full_ns","recompute_subset_ns"]
        costs[mode]={k:sum(r["coverage"][mode][k] for r in data.values()) for k in fields}
    events={}
    for mode in ("record","winner","random"):
        ranks=[r["projections"][mode]["rank"] for r in data.values()]
        events[mode]={"unavailable":ranks.count(None),"topk":{str(k):sum(i is not None and i<=k for i in ranks) for k in (1,8,64)},
                      "median_rank":median(v for v in ranks if v is not None),"max_rank":max(v for v in ranks if v is not None)}
    stats={k:aggregate([r[k] for r in data.values()]) for k in ("candidates","state_bytes","zlib_bytes","logit_bytes","max_payload_bytes","base_windows")}
    metrics={m:[100*fmean(r["answers"][m][i] for r in qa.values()) for i in (0,1)] for m in next(iter(qa.values()))["answers"]}
    groups=defaultdict(list)
    for q,v in qa.items():groups[v["article"]].append(float(data[q]["same_surface"]))
    values=np.array([fmean(v) for _,v in sorted(groups.items())]);rng=np.random.default_rng(28982)
    interval=np.quantile(values[rng.integers(0,len(values),(20000,len(values)))].mean(axis=1),[.025,.975]).tolist()
    save(HERE/"qa-outcomes.json.gz",qa)
    out={"cohort":len(qa),"articles":len(groups),"full_onnx":sum(len(v["windows"]) for r in states.values() for v in r["states"].values()),
         "same_surface":sum(r["same_surface"] for r in data.values()),"same_address":sum(r["same_source"] for r in data.values()),
         "same_surface_ci95":interval,"has_gold_after_retract":sum(v["gold_in_residual"] for v in qa.values()),"model_work":costs,
         "metrics":metrics,"storage":stats,"topk":events,"decisions":seal["decisions"],"qa":sha(HERE/"qa-outcomes.json.gz")}
    save(HERE/"results.json",out);print(out)
if __name__=="__main__":main()

