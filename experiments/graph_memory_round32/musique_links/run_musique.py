"""Predict one next read and verify macro support F1 using the authors' metric."""
from collections import defaultdict
import json
from pathlib import Path
import sys
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"observed_transfer"))
from transfer import Evidence,choose,local_static,catalog,ranks,tie,E5,Tokenizer,sha,put,get
from evaluate import ci
PRIVATE=Path("D:/CodexResearch/x20-r32-musique")
SRC=PRIVATE/"musique.jsonl"
SRC_SHA="15fa63794d18a94ce12411aca6e2327e65b6e83b0b1490efab3f1962e48abf3b"
def data():
    with SRC.open(encoding="utf8") as f:
        for line in f:yield json.loads(line)
def predict():
    assert sha(SRC)==SRC_SHA
    plan={"source":SRC_SHA,"protocol":sha(HERE/"PROTOCOL_RU.md"),"code":sha(Path(__file__)),
          "prior":sha(HERE.parent/"observed_transfer"/"transfer.py"),"tokenizer":sha(E5/"tokenizer.json")}
    put(HERE/"plan.json",plan);tok=Tokenizer.from_file(str(E5/"tokenizer.json"));results={}
    for r in data():
        q=r["id"];ps=r["paragraphs"];query=r["question"];idx=sorted(range(len(ps)),key=lambda i:tie(q+"|musique|"+str(ps[i]["idx"])))
        ts=[ps[i]["title"] for i in idx];reader=Evidence(idx,[[p["paragraph_text"]] for p in ps],tok)
        rec=choose(query,ts,reader,qid=q);seed=rec["seed"];m=rec["mentions"];next_ids=rec["next"]
        next_ids["local_static"]=local_static(query,ts,reader.snippet,seed,m)
        p=ranks(catalog(query,ts)[2](query));cand=[i for i in p if i!=seed]
        for name in ("first_mention","frequent","frequency_position"):
            def key(j):
                pos=m.get(str(j),[])
                first=min(pos,default=99999) if name!="frequent" else 0
                frequency=-len(pos) if name!="first_mention" else 0
                return not pos,frequency,first,p[j]
            next_ids[name]=min(cand,key=key)
        assert reader.read_ids==[seed] and q not in results
        results[q]={"seed":ps[idx[seed]]["idx"],"next":{k:ps[idx[v]]["idx"] for k,v in next_ids.items()},"tokens":rec["tokens"],"n_links":len(m)}
    put(HERE/"predictions.json.gz",results);put(HERE/"seal.json",{"predictions":sha(HERE/"predictions.json.gz"),"plan":sha(HERE/"plan.json")})
def evaluate():
    sys.path.insert(0,str(PRIVATE/"author"))
    from metrics.support import SupportMetric
    assert sha(SRC)==SRC_SHA and get(HERE/"seal.json")["predictions"]==sha(HERE/"predictions.json.gz")
    out={};pred=get(HERE/"predictions.json.gz");metrics=defaultdict(SupportMetric)
    for r in data():
        q=r["id"];assert r["answerable"];gold={p["idx"] for p in r["paragraphs"] if p["is_supporting"]}
        a=pred[q];seed=a["seed"];hits={}
        for k,j in a["next"].items():
            selected={seed,j};assert len(selected)==2
            hits[k]=len(gold & selected);metrics[k](list(selected),list(gold))
        out[q]={"g":len(gold),"hits":hits,"seed_hit":int(seed in gold),"tokens":a["tokens"]}
    assert set(out)==set(pred)
    two=[r for r in out.values() if r["g"]==2];used=list(metrics)
    def compare(k):
        delta=[int(r["hits"]["local_static"]==2)-int(r["hits"][k]==2) for r in two]
        return {"delta_pp":100*np.mean(delta),"CI95_pp":ci(delta),"wins":delta.count(1),"losses":delta.count(-1)}
    scores={}
    for k,metric in metrics.items():
        avg=np.mean([2*r["hits"][k]/(2+r["g"]) for r in out.values()])
        assert abs(avg-metric.get_metric()[1])<1e-10
        scores[k]={"author_support_f1":metric.get_metric()[1],"two_exact":sum(r["hits"][k]==2 for r in two)}
    put(HERE/"outcomes.json.gz",out)
    put(HERE/"results.json",{"n":len(out),"n_two":len(two),"n_seed_two":sum(r["seed_hit"] for r in two),"score":scores,
        "local_minus":{k:compare(k) for k in ("mention_title","first_mention","frequency_position","frequent","title")},
        "author_source":{p.name:sha(p) for p in (PRIVATE/"author"/"metrics").glob("*.py")},"mean_tokens":np.mean([r["tokens"] for r in out.values()]),"counts_by_hops":{str(k):sum(r["g"]==k for r in out.values()) for k in sorted({r["g"] for r in out.values()})}})
if __name__=="__main__":
    if sys.argv[1]=="predict":predict()
    elif sys.argv[1]=="score":evaluate()
    else:raise ValueError("Specify predict or score")
