"""Forecast exactly one unseen repository. Its own outcome file is never opened."""
import time
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from common import *


def run(repo):
    fs=read(D/"feature-seal.json");ls=read(D/"label-seal.json");assert ls["features"]==sha(D/"feature-seal.json")
    rows=read(D/"features.json.gz");assert fs["features"]==sha(D/"features.json.gz") and repo in fs["repos"]
    train={};files=[]
    for other in fs["repos"]:
        if other==repo:continue
        name,digest=ls["files"][other];assert sha(D/name)==digest
        labels=read(D/name);assert all(rows[k]["repo"]==other for k in labels)
        train.update(labels);files.append([other,name,digest])
    hold={k for k,r in rows.items() if r["repo"]==repo}
    assert set(train).isdisjoint(hold) and set(train)|hold==rows.keys()
    X=[];Y=[];w=[];sources=set()
    for key,lab in train.items():
        bs=[b for b in rows[key]["blocks"] if b["target"] and b["novel"]]
        for b in bs:
            y=int(lab["matches"][str(b["idx"])]>0);X.append(b["x"]);Y.append(y);w.append(1/len(bs))
            if y:sources.add(rows[key]["issue"])
    active=sum(Y)>=20 and len(sources)>=5
    params={}
    if active:
        norm=StandardScaler().fit(X,sample_weight=w)
        model=LogisticRegression(C=0.5,class_weight="balanced",max_iter=1000,random_state=43).fit(norm.transform(X),Y,sample_weight=w)
        params=dict(center=norm.mean_.tolist(),scale=norm.scale_.tolist(),weights=model.coef_[0].tolist(),
                    intercept=float(model.intercept_[0]),C=0.5)
    forecasts={}
    for key in sorted(hold):
        bs=rows[key]["blocks"]
        out={m:choose(bs,weights(bs,m)) for m in METHODS if m!="model"}
        assert out["original"]==rows[key]["original"]
        valid=[b for b in bs if b["target"] and b["novel"]]
        if active and valid:
            prob=model.predict_proba(norm.transform([b["x"] for b in valid]))[:,1]
            values={b["idx"]:int(round(1000000*v)) for b,v in zip(valid,prob)}
            out["model"]=choose(bs,values)
        else:out["model"]=out["near"]
        head,remaining=prefix(bs);charge={b["idx"]:b["cost"] for b in bs}
        assert all(v[:len(head)]==head and len(v)==len(set(v)) and sum(charge[u] for u in v)<=2048 for v in out.values())
        forecasts[key]=out
    path="ranks-"+repo[:12]+".json.gz";save(path,forecasts)
    save("seal-"+repo[:12]+".json",dict(held_repo=repo,train_files=files,test_states=len(hold),train_states=len(train),
                                       training_blocks=len(Y),positive_blocks=sum(Y),positive_issues=len(sources),
                                       active=active,parameters=params,rows=sha(D/path),program=sha(D/"rank.py"),
                                       features=sha(D/"features.json.gz")))
    print("Fold",repo[:10],"test",len(hold),"train positives",sum(Y),"positive issues",len(sources),"fitted",active,flush=True)


if __name__=="__main__":
    import sys
    if len(sys.argv)!=2:raise SystemExit("rank.py <repo-sha>")
    run(sys.argv[1])

