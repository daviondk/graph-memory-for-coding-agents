"""Freeze a distinct lexical R39 model, evaluate its OOF controls and export Test500 offline."""
from panel import *
import os
for envname in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[envname]="1"
from collections import Counter
from functools import lru_cache
import math
import re
import numpy as np
sys.path.insert(0,str(ROOT.parent/"repo_crossfit"))
from fit_crossfit import estimate, serial_model, certify, fold_by_repository
from data import norm,tokens,splitwords,rank,order,labels
from prepare import baseline,SEC,WP,QW
from serbench.scoring import validate_predictions
from tokenizers import Tokenizer

METHOD = "R39-Lexical-Residual"
FIELDS = ("issue","information_need","current_subgoal","current_hypothesis","current_observation",
          "search_queries","opened_files")
tokenizers = [Tokenizer.from_file(str(p)) for p in (WP,QW)]
for t in tokenizers:
    t.no_truncation()
    t.no_padding()


@lru_cache(maxsize=50_000)
def costs(path,excerpt):
    rendered = path+"\n"+excerpt+"\n\n"
    return tuple(len(t.encode(rendered,add_special_tokens=False).ids) for t in tokenizers)


def features(item):
    cs = sorted(item["candidate_evidence"],key=lambda c:c["evidence_id"])
    ids = [x["evidence_id"] for x in cs]
    observed = np.array([c["observed_by_state"] for c in cs],float)
    filepaths=[norm(c["source_path"]) for c in cs]
    tests = np.array([bool(re.search(r"(^|[/_.-])tests?([/_.-]|$)",p)) for p in filepaths],float)
    words = [tokens(c["content_excerpt"]) for c in cs]
    cwd = [w|splitwords(w) for w in words]
    ranks = rank(baseline._bm25_scores(baseline._query(item),[baseline._candidate_text(c) for c in cs]))
    wp,qw = np.array([costs(c["source_path"],c["content_excerpt"]) for c in cs]).T
    z=np.zeros(len(ids))
    cols = [z,z,np.log1p(ranks),z,z,z,z,np.log1p(wp),z,z,np.log1p(qw),
            observed,tests,np.log1p([p.count("/") for p in filepaths]),np.log1p([len(w) for w in words])]
    path_words = [set(re.findall(r"[a-z0-9]{2,}",p)) for p in filepaths]
    counts=Counter(t for w in cwd for t in w)
    idf={t:math.log1p(len(cs)/(1+cnt)) for t,cnt in counts.items()}
    for field in FIELDS:
        value = item.get(field) or ""
        literal = (value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)).lower()
        query=tokens(value)
        query|=splitwords(query)
        weighted=np.array([sum(idf[t] for t in sorted(bag&query)) for bag in cwd])
        query_tests=bool(re.search(r"\b(test|tests|verify|failure|assertion)\b",literal))
        cols += [weighted/(1+sum(idf.get(t,0) for t in sorted(query))),np.log1p(rank(weighted)),
                 [len(bag&query)/(1+len(bag)) for bag in path_words],
                 [bool(p) and p in literal for p in filepaths],
                 [bool(p) and p.rsplit("/",1)[-1] in literal for p in filepaths],tests*query_tests]
    return dict(ids=ids,repo=item["repo"],qw=qw.tolist(),bm25=ranks.tolist()),np.column_stack(cols).astype(np.float32)


def load_split(split):
    with gzip.open(PUB.parent/split/"items.jsonl.gz","rt",encoding="utf8") as f:
        items=list(map(json.loads,f))
    excluded={r["instance_id"] for r in items if SEC.search(r["issue"]+" "+str(r.get("information_need",""))+" "+r["repo"])}
    dataset,rows,X={}, {}, {}
    for r in items:
        q=r["state_id"]
        # The SDK only needs candidate IDs and observed IDs to validate ranks.
        dataset[q]={"state_id":q,"candidate_evidence":[{"evidence_id":c["evidence_id"]} for c in r["candidate_evidence"]],
                    "observed_evidence_ids":r["observed_evidence_ids"]}
        if r["instance_id"] in excluded:
            continue
        rows[q],X[q]=features(r)
    return dataset,rows,X


def run():
    original,rows,X=load_split("cal500")
    assert len(original)==500 and len(rows)==494
    cached=read(R34/"features.json.gz")
    assert rows.keys()==cached.keys()
    for q,r in rows.items():
        assert r["bm25"]==cached[q]["ranks"]["bm25"] and r["qw"]==cached[q]["qw"]
    folds=fold_by_repository(rows)
    assert folds==read(ROOT.parent/"repo_crossfit/selection.json")["folds"]
    pred,all_models={},{}
    for fold in range(5):
        train={q for q,r in rows.items() if folds[r["repo"]] not in (fold,(fold+1)%5)}
        test=sorted(q for q,r in rows.items() if folds[r["repo"]]==fold)
        cert=certify(rows,labels(train))
        models={k:estimate(rows,X,cert,k)[0] for k in ("proposed","no_observed")}
        all_models[str(fold)]={m:serial_model(v) for m,v in models.items()}
        for q in test:
            ids=rows[q]["ids"]
            bm25=-np.array(rows[q]["bm25"],float)
            predicted=dict(bm25=order(bm25),bm25_seen=order(bm25-1e5*X[q][:,11]))
            for k,model in models.items():
                xx=X[q].copy()
                if k=="no_observed":
                    xx[:,11]=0
                predicted[k]=order(model.decision_function(xx))
            pred[q]={k:[ids[j] for j in ordering[:8]] for k,ordering in predicted.items()}
    assert pred.keys()==rows.keys()
    model,training=estimate(rows,X,certify(rows,labels(set(rows))),"proposed")
    all_models["final"]=serial_model(model)
    models_path=ROOT/"blind-models.json.gz"
    models_path.write_bytes(gzip.compress((json.dumps(all_models,sort_keys=True,separators=(",",":"))+"\n").encode(),mtime=0))
    write("blind-cal-forecasts.json",pred)
    dataset,blind,Z=load_split("test500")
    assert len(dataset)==500 and not (set(folds)&{r["repo"] for r in blind.values()})
    outputs=[]
    for q in sorted(dataset):
        seq=[]
        if q in blind:
            seq=[blind[q]["ids"][j] for j in order(model.decision_function(Z[q]))[:8]]
        outputs.append({"method":METHOD,"ranked_evidence_ids":seq,"state_id":q})
    destination=ROOT/"test500-lexical-residual.jsonl"
    with destination.open("w",encoding="utf8",newline="\n") as fp:
        for r in outputs:
            fp.write(json.dumps(r,sort_keys=True,separators=(",",":"))+"\n")
    validation=validate_predictions(destination,dataset.values(),strict=True)
    assert destination.stat().st_size<=2*2**20
    write("blind-seal.json",dict(protocol=sha(ROOT/"BLIND_PROTOCOL_RU.md"),code=sha(Path(__file__)),training=training,
         calibration=sha(ROOT/"blind-cal-forecasts.json"),blind=sha(destination),models=sha(models_path),coverage=len(blind),
         abstained=len(dataset)-len(blind),bytes=destination.stat().st_size,validation=validation))
    print("validated 500 states, answered", len(blind),"abstained",len(dataset)-len(blind))


if __name__=="__main__":
    run()
