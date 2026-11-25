"""Learn a dev-only, query-local call decision before reading any test labels."""
from collections import Counter
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from tokenizers import Tokenizer

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
R19=WORK/"graph_memory_round19"; R18=WORK/"graph_memory_round18"
GRAPH=ROOT.parent/"residual_graph"; TR=R19/"trained_rank"; OFF=R18/"isetrace_official"
DATA=Path(os.environ.get("X20_DATA","D:/CodexResearch"))
PROJECTIONS={"dev":DATA/"x20-isetrace-runtime/write-dev-private/projection","test":DATA/"x20-isetrace-e5-gpu/cache/projection"}
TOKENIZER=DATA/"x20-isetrace-runtime/inputs/tokenizer.json"
sys.path.insert(0,str(DATA/"x20-isetrace-runtime/upstream"))
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
from graph_memory.trajectories import SourceSpan
from graph_memory.retrieval.results import RankedNodeRecord

FEATURES=["log_query_wordpieces","connectives","log_candidate_count","first_score","margin_1_2","margin_1_5",
          "sd_first10","top5_field_fraction","top10_max_field_fraction","top5_output_fraction","top5_mean_cost_over_504",
          "log_skip_sources","skip_free_fraction"]
CONNECT=re.compile(r"\b(?:and|or|both|between|before|after|then)\b",re.I)
QUOTAS=[25,50,75]


def hashstr(s):
    if isinstance(s,str):s=s.encode()
    return hashlib.sha256(s).hexdigest()


def sha(path):return hashstr(path.read_bytes())


def load(path):
    with (gzip.open(path,"rt",encoding="utf8") if path.suffix==".gz" else path.open(encoding="utf8")) as f:return json.load(f)


def put(path,x):
    raw=(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n").encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix==".gz" else raw)


def choose_skip(row):
    used=0;chosen=[]
    for n in row["rr"]:
        if used+n["token_count"]<=2048:
            used+=n["token_count"];chosen.append(n)
    if "arms" in row:
        assert [n["node_id"] for n in chosen]==row["arms"]["skip"]
    return chosen,used


def matched_pool(row):
    values=[(n["node_id"],n["token_count"],[(s["event_id"],s["json_pointer"],s["char_start"],s["char_end"]) for s in n["source_spans"]])
            for n in row["rr"]]
    assert len({v[0] for v in values})==len(values)
    return hashstr(json.dumps(sorted(values),ensure_ascii=False,separators=(",",":")))


def fields(node):
    spans=node["source_spans"];assert len(spans)==1
    return spans[0]["event_id"],spans[0]["json_pointer"]


def features(row,question,tok):
    rr=row["rr"];assert rr
    first=rr[0]["score"];top5=rr[:5];top10=rr[:10];loc=[fields(n) for n in top10]
    picked,used=choose_skip(row)
    return [math.log1p(len(tok.encode(question,add_special_tokens=False).ids)),len(CONNECT.findall(question)),math.log1p(len(rr)),
            first,first-rr[min(1,len(rr)-1)]["score"],first-top5[-1]["score"],float(np.std([n["score"] for n in top10])),
            len(set(loc[:5]))/len(top5),max(Counter(loc).values())/len(top10),sum(p=="/content" for e,p in loc[:5])/len(top5),
            sum(n["token_count"] for n in top5)/(len(top5)*504),math.log1p(len({fields(n) for n in picked})),(2048-used)/2048]


def fit_skips(rows,gold):
    values={}
    for row in rows:
        q=row["q"];chosen,_=choose_skip(row)
        v=span_metrics_under_token_budget(tuple(RankedNodeRecord.model_validate(n) for n in chosen),
          tuple(SourceSpan.model_validate(s) for s in gold[q]),2048)
        values[q]=int(v.full_support)
    return values


def dense_sources():
    dev=GRAPH/"dev500-pu-dense-ranks.json.gz";devhash=load(GRAPH/"dev500-pu-dense-lock.json")["ranks"]
    assert devhash==sha(dev)
    trseal=load(TR/"forecast-seal.json")["forecasts"]
    test=[TR/f"forecasts-main-{i}.json.gz" for i in range(8)]
    assert all(trseal[p.name]==sha(p) for p in test)
    return {"dev":[dev],"test":test}


def prepare():
    st=time.perf_counter()
    paths=dense_sources()
    inp={p.name:sha(p) for seq in paths.values() for p in seq}
    split=load(TR/"split.json.gz")
    assert not {x["t"] for x in split["test"]}&{x["t"] for x in split["dev"]}
    tok=Tokenizer.from_file(str(TOKENIZER));tok.no_padding();tok.no_truncation()
    put(ROOT/"plan.json",dict(protocol=sha(ROOT/"PROTOCOL_RU.md"),code=sha(ROOT/"gate.py"),dense_ranks=inp,
        tokenizer=sha(TOKENIZER),split=sha(TR/"split.json.gz"),features=FEATURES,alpha=25.0,quotas=QUOTAS))
    timings={}
    for name in ["dev","test"]:
        start=time.perf_counter();queries={}
        for p in sorted(PROJECTIONS[name].glob("*.json.gz")):
            pr=load(p);queries.update({q:(pr["t"],text) for q,text in pr["q"]})
        control={r["q"]:r["t"] for r in split[name]};records=[]
        for f in paths[name]:
            for r in load(f):
                q,t=r["q"],r["t"];assert q in queries and queries[q][0]==t==control[q]
                records.append(dict(q=q,t=t,z=features(r,queries[q][1],tok),pool=matched_pool(r)))
        assert len(records)==len(control) and set(control)=={r["q"] for r in records}
        put(ROOT/f"{name}-features.json.gz",records);timings[name]=time.perf_counter()-start
    # No test labels are loaded in prepare, fit or predict.
    dg=load(R19/"write_transfer/gold-spans.json.gz");vals=fit_skips(load(paths["dev"][0]),dg)
    put(ROOT/"dense-dev-support.json",vals)
    out=["dev-features.json.gz","test-features.json.gz","dense-dev-support.json","plan.json"]
    put(ROOT/"feature-seal.json",dict(files={n:sha(ROOT/n) for n in out},seconds=timings,all_seconds=time.perf_counter()-st))


def tie(q,arm):
    return hashstr("R20 gate tie|"+arm+"|"+q)


def threshold(points,fraction):
    rows=sorted(points,key=lambda x:(-x[0],x[1]));k=round(len(rows)*fraction/100)
    s,key=rows[k-1];return [s,key]


def call(score,q,arm,th):
    return (-score,tie(q,arm))<=(-th[0],th[1])


def validate_gate_inputs():
    src=load(ROOT/"feature-seal.json")
    assert all(sha(ROOT/n)==h for n,h in src["files"].items())
    cfg=load(ROOT/"plan.json");assert cfg["code"]==sha(ROOT/"gate.py") and cfg["features"]==FEATURES


def fit(graph_dev,source_sha,tag):
    validate_gate_inputs()
    assert sha(graph_dev)==source_sha
    dense=load(ROOT/"dense-dev-support.json")
    rows=sorted(load(ROOT/"dev-features.json.gz"),key=lambda r:r["q"])
    gr=load(graph_dev);assert len(gr)==500 and set(dense)=={r["q"] for r in gr}
    index={r["q"]:r for r in rows}
    if "rr" in gr[0]:
        assert all(r["t"]==index[r["q"]]["t"] and matched_pool(r)==index[r["q"]]["pool"] for r in gr)
        graph=fit_skips(gr,load(R19/"write_transfer/gold-spans.json.gz"))
    else:
        assert all(r["t"]==index[r["q"]]["t"] and r["pool"]==index[r["q"]]["pool"] for r in gr)
        graph={r["q"]:int(r["full_support"]) for r in gr}
    t0=time.perf_counter()
    x=np.array([r["z"] for r in rows]);y=np.array([graph[r["q"]]-dense[r["q"]] for r in rows])
    mean=x.mean(0);sd=x.std(0);sd[sd==0]=1;z=(x-mean)/sd
    coef=np.linalg.solve(z.T@z+25*np.eye(z.shape[1]),z.T@(y-y.mean()))
    # Use exactly the same scalar arithmetic as at deployment, including tie breaks.
    info=dict(means=mean.tolist(),scale=sd.tolist(),coef=coef.tolist(),intercept=float(y.mean()))
    thresh={}
    for arm in ["gate","margin"]:
        pts=[(raw_score(r,info,arm),tie(r["q"],arm)) for r in rows]
        thresh[arm]={str(k):threshold(pts,k) for k in QUOTAS}
        assert all(sum(call(raw_score(r,info,arm),r["q"],arm,thresh[arm][str(k)]) for r in rows)==5*k for k in QUOTAS)
    out={**info,"alpha":25,"dev_targets":dict(Counter(map(int,y))),"dev_dense":sum(dense.values()),"dev_graph":sum(graph.values()),
        "cutoffs":thresh,"feature_sha":sha(ROOT/"feature-seal.json"),"graph_dev_sha":source_sha,"tag":tag,"seconds_fit":time.perf_counter()-t0}
    put(ROOT/f"{tag}-model.json",out)


def raw_score(row,model,arm):
    if arm=="margin":return -row["z"][4]
    vals=np.asarray(row["z"]);return float(np.dot((vals-np.asarray(model["means"]))/np.asarray(model["scale"]),model["coef"])+model["intercept"])


def predict(tag):
    validate_gate_inputs();M=load(ROOT/(tag+"-model.json"));X=load(ROOT/"test-features.json.gz");st=time.perf_counter()
    assert M["feature_sha"]==sha(ROOT/"feature-seal.json")
    out=[]
    for r in X:
        q,t=r["q"],r["t"]
        scores={a:raw_score(r,M,a) for a in ["gate","margin"]}
        choice={a+str(k):call(s,q,a,M["cutoffs"][a][str(k)]) for a,s in scores.items() for k in QUOTAS}
        out.append(dict(q=q,t=t,s=scores,call=choice))
    order=sorted(out,key=lambda x:hashstr("R20 matched random calls|"+x["q"]))
    for k in QUOTAS:
        size=sum(r["call"]["gate"+str(k)] for r in out)
        for i,r in enumerate(order):r["call"]["random"+str(k)]=i<size
    put(ROOT/(tag+"-decisions.json.gz"),out)
    put(ROOT/(tag+"-decision-seal.json"),dict(decisions=sha(ROOT/(tag+"-decisions.json.gz")),model=sha(ROOT/(tag+"-model.json")),
        inputs=sha(ROOT/"feature-seal.json"),test=2000,seconds_decide=time.perf_counter()-st))


if __name__=="__main__":
    if sys.argv[1]=="prepare":prepare()
    elif sys.argv[1]=="fit":fit(Path(sys.argv[2]),sys.argv[3],sys.argv[4])
    elif sys.argv[1]=="predict":predict(sys.argv[2])
