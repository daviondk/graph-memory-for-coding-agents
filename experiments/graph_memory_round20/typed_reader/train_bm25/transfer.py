"""Train on official train-only BM25 ranks and transfer fixed coefficients to the original Dense-FT test ranks."""
import collections
import hashlib
import os
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import study as s
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from graph_memory.retrieval.methods.flat.bm25 import BM25TaskRetriever
from graph_memory.retrieval.requests import TextRankingRequest,TextCandidate

def fit():
    lock=s.read(s.HERE/"prediction-plan.json")
    x0=s.read(s.TR/"split.json.gz")
    allowed={r["q"]:r["t"] for r in x0["train"]}
    stages=[{r["t"] for r in x0[k]} for k in ("train","dev","test")]
    assert not stages[0]&stages[1] and not stages[0]&stages[2] and not stages[1]&stages[2]
    manifest=dict(protocol=s.sha(HERE/"PROTOCOL_RU.md"),main_plan=s.sha(s.HERE/"prediction-plan.json"),
        code=s.sha(Path(__file__)),main_code=s.sha(s.HERE/"study.py"),split=s.sha(s.TR/"split.json.gz"),queries=len(allowed))
    s.put(HERE/"plan.json",manifest)
    ix=s.graph_index()
    X={a:[] for a in s.MODELS};ys=[];weights=[];seen=set();excluded=0
    bm=BM25TaskRetriever()
    h=hashlib.sha256()
    for j,t in enumerate(sorted(stages[0]),1):
        file=s.PROJ/"projection/train"/(t+".json.gz")
        h.update(t.encode()+bytes.fromhex(s.sha(file)))
        rec=s.read(file);gr=s.project(t,ix)
        pool=tuple(TextCandidate.model_validate(r) for r in rec["pool"])
        for q in rec["qs"]:
            assert q["q"] not in seen and allowed[q["q"]]==t
            seen.add(q["q"])
            rq=TextRankingRequest(task_id=q["q"],query_text=q["text"],candidates=pool)
            ranked=bm.rank(rq)
            rr=[dict(node_id=n.node_id) for n in ranked]
            pos=set(q["positive"]);assert pos<={x.node_id for x in ranked}
            y=np.array([n.node_id in pos for n in ranked],dtype=int)
            n1=int(y.sum());n0=len(y)-n1
            if not n1 or not n0:
                excluded+=1;continue
            x=s.project_rows(rr,gr)
            for a in s.MODELS:X[a].append(x[a])
            ys.append(y);weights.append(np.where(y,.5/n1,.5/n0))
        if j%500==0:print("native train trajectories",j,"/",len(stages[0]),flush=True)
    assert seen==set(allowed)
    y=np.concatenate(ys);w=np.concatenate(weights);w*=len(w)/w.sum()
    models={}
    for a in s.MODELS:
        x=np.concatenate(X[a]);sc=StandardScaler().fit(x,sample_weight=w)
        z=LogisticRegression(C=1,solver="lbfgs",max_iter=1000,random_state=13).fit(sc.transform(x),y,sample_weight=w)
        W=z.coef_[0]/sc.scale_;b=float(z.intercept_[0]-W@sc.mean_)
        assert max(z.n_iter_)<1000 and np.allclose(x@W+b,z.decision_function(sc.transform(x)),rtol=1e-10,atol=1e-10)
        models[a]=dict(w=W.tolist(),bias=b,n_input=len(W),n_iter=int(z.n_iter_[0]))
    s.put(HERE/"weights.json",models)
    s.put(HERE/"fit-seal.json",dict(inputs=s.sha(HERE/"plan.json"),weights=s.sha(HERE/"weights.json"),queries=len(seen),
        excluded=excluded,nodes=len(y),positive=int(y.sum()),trajectories=len(stages[0]),training_projection=h.hexdigest()))
    print("BM25 transfer weights sealed",len(seen),len(y),int(y.sum()),flush=True)

def predict():
    seal=s.read(HERE/"fit-seal.json")
    assert seal["weights"]==s.sha(HERE/"weights.json")
    assert s.read(HERE/"plan.json")["code"]==s.sha(Path(__file__))
    models=s.read(HERE/"weights.json");ix=s.graph_index();hashes={};seen=set()
    for i in range(8):
        f=s.TR/f"forecasts-main-{i}.json.gz"
        assert s.sha(f)==s.read(s.HERE/"prediction-plan.json")["test"][f.name]
        dest=HERE/f"forecast-{i}.json.gz"
        by=collections.defaultdict(list)
        for r in s.read(f):by[r["t"]].append(r)
        out=[]
        for t,group in sorted(by.items()):
            gr=s.project(t,ix)
            for r in group:
                rr=r["rr"];x=s.project_rows(rr,gr);cost=[n["token_count"] for n in rr]
                selected={}
                for a in s.ARMS:
                    if a=="dense":
                        order=np.arange(len(rr))
                    else:
                        v=x["shuffled" if a=="typed_on_shuffled" else a]
                        m=models["typed" if a=="typed_on_shuffled" else a]
                        order=np.argsort(-(v@np.asarray(m["w"])+m["bias"]),kind="stable")
                    selected[a]={p:s.pack(order,cost,p=="skip") for p in ("prefix","skip")}
                assert r["q"] not in seen
                seen.add(r["q"])
                out.append(dict(q=r["q"],t=t,selection=selected))
        s.put(dest,out);hashes[dest.name]=s.sha(dest)
        print("BM25 -> Dense shard",i,flush=True)
    assert seen=={r["q"] for r in s.read(s.TR/"split.json.gz")["test"]}
    s.put(HERE/"forecast-seal.json",dict(fit=s.sha(HERE/"fit-seal.json"),forecasts=hashes,q=len(seen),t=1207))
if __name__=="__main__":
    if sys.argv[1]=="fit":fit()
    else:predict()
