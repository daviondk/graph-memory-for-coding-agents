"""Called only after all model answers are sealed. Uses the authors' public AnswerMetric."""
import json
import numpy as np
from common import *
from grade47 import unit,analyze,AnswerMetric

def main():
    check()
    ans_seal=get(D/"answer-seal.json");ins=get(D/"input-seal.json")
    assert ans_seal["input"]==sha(D/"input-seal.json") and ans_seal["answers"]==sha(D/"answers.json.gz")
    assert ins["contexts"]==sha(D/"contexts.json.gz") and ins["delivered"]==sha(P/"delivered.json.gz")
    data=get(D/"contexts.json.gz");out=get(D/"answers.json.gz");texts=get(P/"delivered.json.gz")
    meters={a:AnswerMetric() for a in ARMS};rows={};gold={}
    path=P/"official-dev.jsonl";assert sha(path)==get(D/"source-seal.json")["splits"]["dev"]["official_sha256"]
    with path.open(encoding="utf8") as f:
        for line in f:
            r=json.loads(line);q=r["id"];assert q not in rows and r["answerable"]
            v=data[q];truth=[r["answer"],*r["answer_aliases"]];ids=sorted(p["idx"] for p in r["paragraphs"] if p["is_supporting"])
            gold[q]=[truth,ids]
            scores=unit(q,truth,ids,v,texts,out)
            for a,(_,k,_) in v["refs"].items():meters[a](out[k]["answer"],truth)
            rows[q]=dict(arms=scores,cluster=v["cluster"],switch=v["switch"],hops=len(ids),
                         successful=v["successful"],seen_r46=v["seen"]["r46_train_panel"],seen_train=v["seen"]["full_train"],
                         any_r46=v["any_seen"]["r46_train_panel"],any_train=v["any_seen"]["full_train"])
    assert set(rows)==set(data) and len(rows)==2417
    all_rows=list(rows.values())
    for a,m in meters.items():
        assert np.allclose(m.get_metric(),np.mean([r["arms"][a][:2] for r in all_rows],axis=0),rtol=0,atol=1e-12)
    groups={"all":all_rows,"switched":[r for r in all_rows if r["switch"]],"unchanged":[r for r in all_rows if not r["switch"]],
            "placebo_changed_first_seed":[r for r in all_rows if r["successful"]]}
    for n in sorted({r["hops"] for r in all_rows}):groups["hops_"+str(n)]=[r for r in all_rows if r["hops"]==n]
    for label in ("seen_r46","seen_train"):
        for hit in (True,False):groups[label+"_"+str(hit)]=[r for r in all_rows if r[label]==hit]
    for label in ("any_r46","any_train"):
        groups["no_"+label]=[r for r in all_rows if not r[label]]
    cache={};summary={}
    for group,subset in groups.items():
        # All seven arrays are identical for duplicate predefined subsets only.
        ids=tuple(id(r) for r in subset)
        if ids not in cache:cache[ids]=analyze(subset)
        summary[group]=cache[ids]
    lengths=[v["refs"]["true"][2] for v in data.values()]
    put(D/"gold.json.gz",gold);put(D/"outcomes.json.gz",rows)
    put(D/"results.json",dict(groups=summary,metrics=["EM","AnswerF1","complete_support","answer_string"],
        denominators={k:len(v) for k,v in groups.items()},clusters=len({r["cluster"] for r in all_rows}),
        mean_input=float(np.mean(lengths)),min_input=min(lengths),max_input=max(lengths),
        primary_different_sequences=sum(v["refs"]["true"][1]!=v["refs"]["lex"][1] for v in data.values()),
        common_shortened=sum(v["n"]<v["original_n"] for v in data.values()),
        input=sha(D/"input-seal.json"),answers=sha(D/"answer-seal.json"),grade=sha(Path(__file__)),
        outcomes=sha(D/"outcomes.json.gz"),gold=sha(D/"gold.json.gz")))
    print(summary["all"]["means"],summary["all"]["contrasts"]["true-lex"],flush=True)
if __name__=="__main__":main()
