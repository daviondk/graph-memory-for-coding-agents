"""Disjoint-domain fit, threshold calibration and pre-evaluation prediction seals."""
from pathlib import Path
from itertools import chain
from hashlib import sha256
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from project import OUT,PRIV,save,get
from features import GROUPS,extract

MODELS={"position":["position"],"graph":["graph"],"lexical":["lexical"],"graph_pos":["graph","position"],"selective":["graph","position","lexical"]}
def matrix(rows,names,labels=None):
    keys=[(r["id"],u) for r in rows for u in r["order"]]
    x=np.array([[r["features"][u][n] for n in names] for r in rows for u in r["order"]],dtype=float).reshape(-1,len(names))
    y=None if labels is None else np.array([u in labels[q] for q,u in keys],int)
    return x,y,keys

def model(train,ys):
    assert set(ys)=={0,1}
    return make_pipeline(StandardScaler(),LogisticRegression(C=1,solver="liblinear",class_weight="balanced",random_state=29,max_iter=1000)).fit(train,ys)

def fitfold(train,test,groups):
    names=list(chain.from_iterable(GROUPS[g] for g in groups))
    splits=sorted(train);ys=[];scores=[];truth_total=0;train_ids=set()
    for d in splits:
        labels=get(PRIV/("train-labels-"+d+".json.gz"))
        assert set(labels)=={r["id"] for r in train[d]}
        train_ids.update(labels);truth_total+=sum(map(len,labels.values()))
    assert train_ids.isdisjoint(r["id"] for r in test)
    pool_labels={k:set(v) for d in splits for k,v in get(PRIV/("train-labels-"+d+".json.gz")).items()}
    for hold in splits:
        xa,ya,_=matrix([r for s in splits if s!=hold for r in train[s]],names,pool_labels)
        xv,yv,_=matrix(train[hold],names,pool_labels)
        mdl=model(xa,ya);scores.extend(mdl.predict_proba(xv)[:,1]);ys.extend(yv)
    ys=np.asarray(ys,bool);scores=np.asarray(scores)
    def key(t):
        picked=scores>=t;tp=(picked&ys).sum()
        f=2*tp/max(1,truth_total+picked.sum())
        return (f,-round(abs(t-0.5),2),t)
    threshold=max([i/20 for i in range(1,20)],key=key)
    xt,yt,_=matrix([r for s in splits for r in train[s]],names,pool_labels);mdl=model(xt,yt)
    xv,_,keys=matrix(test,names);probs=mdl.predict_proba(xv)[:,1]
    receipt=dict(train_domains=splits,train_cases=len(train_ids),train_ids=sorted(train_ids),n_candidates=len(yt),positives=int(yt.sum()),heldout=sorted(r["id"] for r in test),threshold=threshold,inner_micro=float(key(threshold)[0]),
                 features=names,mean=mdl[0].mean_.tolist(),scale=mdl[0].scale_.tolist(),coef=mdl[1].coef_[0].tolist(),intercept=float(mdl[1].intercept_[0]))
    return dict(zip(keys,probs)),receipt
def main():
    by={}
    sources={}
    for p in ("controlled","adapted"):
        raw=get(PRIV/(p+"-blind.json.gz"));features=[extract(x) for x in raw];by[p]=features
        sources[p]=save(PRIV/(p+"-features.json.gz"),features)
    domains=get(PRIV/"controlled-folds.json")
    pool={d:[r for r in by["controlled"] if domains[r["id"]]==d] for d in sorted(set(domains.values()))}
    predictions={"controlled":[],"adapted":[]};fits={}
    for group,tests in list(pool.items())+[("adapted",by["adapted"])]:
        train={d:pool[d] for d in pool if d!=group};recv="adapted" if group=="adapted" else "controlled";params={name:fitfold(train,tests,spec) for name,spec in MODELS.items()}
        fits[group]={name:v[1] for name,v in params.items()}
        for row in tests:
            case=row["id"];src=set(row["source"]);order=row["order"];feat=row["features"]
            direct=[u for u in order if feat[u]["direct"]];goal=[u for u in order if feat[u]["to_final"]]
            arms=dict(reach=order,direct=direct,last=order[-1:],goal=goal,direct_or_goal=sorted(set(direct)|set(goal)))
            for name,(probs,par) in params.items():arms[name]=[u for u in order if probs[(case,u)]>=par["threshold"]]
            arms["top1"]=sorted(order,key=lambda u:(params["selective"][0][(case,u)],order.index(u)))[-1:]
            out={}
            for arm,ids in arms.items():
                memory=set(row["memreach"]) if arm=="reach" else (src if arm=="direct" else src|{m for u in ids for m in row["pathmem"][u]})
                out[arm]=dict(c=sorted(ids),m=sorted(memory))
            predictions[recv].append(dict(id=case,fold=group,arms=out,selective_scores={u:float(params["selective"][0][(case,u)]) for u in order}))
    seal=dict(inputs=get(OUT/"input-receipt.json"),plan=sha256((OUT/"PROTOCOL_RU.md").read_bytes()).hexdigest(),code={p:sha256((OUT/p).read_bytes()).hexdigest() for p in ["project.py","training_labels.py","features.py","predict.py"]},features=sources,fit=save(OUT/"fits.json.gz",fits))
    for p,v in predictions.items():seal[p]=save(OUT/(p+"-forecasts.json.gz"),sorted(v,key=lambda r:r["id"]))
    save(OUT/"forecast-seal.json",seal);print({p:len(v) for p,v in predictions.items()})
if __name__=="__main__":main()

