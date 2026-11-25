"""Additional structural ablative models with native dev or train-only BM25 ranks."""
import collections
import hashlib
import os
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import study as s
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from graph_memory.retrieval.methods.flat.bm25 import BM25TaskRetriever
from graph_memory.retrieval.requests import TextRankingRequest,TextCandidate
from graph_memory.retrieval.execution.results import _candidate_token_count
ARMS=("role","role_cost","degrees","role_degrees","structural_only","role_cost_degrees","full_typed_cost")

def design(rr,gr):
    feat=s.project_rows(rr,gr)
    full=feat["typed"]
    own=feat["rank_only"]
    role=np.array([r["node_id"].startswith("output-content:") for r in rr],dtype=float)
    assert all(r["node_id"].startswith(("output-content:","argument:")) for r in rr)
    cost=np.log1p([r["token_count"] for r in rr])
    deg=full[:,3::3]
    return dict(role=np.column_stack((own,role)),role_cost=np.column_stack((own,role,cost)),degrees=np.column_stack((own,deg)),
      role_degrees=np.column_stack((own,role,deg)),structural_only=np.column_stack((role,deg)),
      role_cost_degrees=np.column_stack((own,role,cost,deg)),full_typed_cost=np.column_stack((full,role,cost)))

def fit(stage):
    assert stage in ("train","dev")
    dest=HERE
    split=s.read(s.TR/"split.json.gz")
    tids=sorted({r["t"] for r in split[stage]})
    ix=s.graph_index()
    by=collections.defaultdict(list)
    if stage=="dev":
        for row in s.read(s.RES/"dev500-pu-dense-ranks.json.gz"):
            by[row["t"]].append(row)
    bm=BM25TaskRetriever()
    X={a:[] for a in ARMS};ys=[];ww=[];seen=set();excluded=0
    s.put(dest/f"plan-{stage}.json",dict(protocol=s.sha(HERE/"PROTOCOL_RU.md"),holdout_protocol=s.sha(HERE.parent/"holdout80/PROTOCOL_RU.md"),
           original=s.sha(s.HERE/"prediction-plan.json"),code=s.sha(Path(__file__)),stage=stage,queries=len(split[stage])))
    for it,t in enumerate(tids,1):
        z=s.read(s.PROJ/"projection"/stage/(t+".json.gz"))
        positive={q["q"]:set(q["positive"]) for q in z["qs"]}
        gr=s.project(t,ix)
        if stage=="train":
            pool=tuple(TextCandidate.model_validate(x) for x in z["pool"])
            costs={v.item_id:_candidate_token_count(v) for v in pool}
            candidates=[]
            for q in z["qs"]:
                rank=bm.rank(TextRankingRequest(task_id=q["q"],query_text=q["text"],candidates=pool))
                candidates.append(dict(q=q["q"],rr=[dict(node_id=n.node_id,token_count=costs[n.node_id]) for n in rank]))
        else:candidates=by[t]
        for r in candidates:
            assert r["q"] not in seen
            seen.add(r["q"])
            y=np.array([n["node_id"] in positive[r["q"]] for n in r["rr"]],dtype=int)
            n1=int(y.sum());n0=len(y)-n1
            if not n1 or not n0:excluded+=1;continue
            feat=design(r["rr"],gr)
            for a in ARMS:X[a].append(feat[a])
            ys.append(y);ww.append(np.where(y,.5/n1,.5/n0))
        if it%500==0:print("ablation",stage,it,"/",len(tids),flush=True)
    assert seen=={q["q"] for q in split[stage]}
    y=np.concatenate(ys);w=np.concatenate(ww);w*=len(w)/w.sum()
    models={}
    for a in ARMS:
        x=np.concatenate(X[a]);sc=StandardScaler().fit(x,sample_weight=w)
        z=LogisticRegression(C=1,solver="lbfgs",max_iter=1000,random_state=13).fit(sc.transform(x),y,sample_weight=w)
        W=z.coef_[0]/sc.scale_;b=float(z.intercept_[0]-W@sc.mean_)
        assert max(z.n_iter_)<1000 and np.allclose(x@W+b,z.decision_function(sc.transform(x)),rtol=1e-10,atol=1e-10)
        models[a]=dict(w=W.tolist(),bias=b,n_input=len(W),n_iter=int(z.n_iter_[0]))
    s.put(dest/f"weights-{stage}.json",models)
    s.put(dest/f"fit-{stage}.json",dict(inputs=s.sha(dest/f"plan-{stage}.json"),weights=s.sha(dest/f"weights-{stage}.json"),
        queries=len(seen),trajectories=len(tids),nodes=len(y),positives=int(y.sum()),excluded=excluded))

def choices(rr,gr,models):
    x=design(rr,gr);cost=[n["token_count"] for n in rr];sel={}
    for arm,m in models.items():
        score=x[arm]@np.array(m["w"])+m["bias"]
        order=np.argsort(-score,kind="stable")
        sel[arm]={p:s.pack(order,cost,p=="skip") for p in ("prefix","skip")}
    return sel

def infer(stage):
    dest=HERE/f"test-{stage}";dest.mkdir(exist_ok=True)
    seal=s.read(HERE/f"fit-{stage}.json")
    assert seal["weights"]==s.sha(HERE/f"weights-{stage}.json")
    assert s.read(HERE/f"plan-{stage}.json")["code"]==s.sha(Path(__file__))
    models=s.read(HERE/f"weights-{stage}.json");ix=s.graph_index();hashes={};allqs=set()
    for i in range(8):
        f=s.TR/f"forecasts-main-{i}.json.gz"
        assert s.sha(f)==s.read(s.HERE/"prediction-plan.json")["test"][f.name]
        by=collections.defaultdict(list)
        for r in s.read(f):by[r["t"]].append(r)
        out=[]
        for t,rs in sorted(by.items()):
            gr=s.project(t,ix)
            for r in rs:
                assert r["q"] not in allqs;allqs.add(r["q"])
                out.append(dict(q=r["q"],t=t,selection=choices(r["rr"],gr,models)))
        f=dest/f"forecast-{i}.json.gz";s.put(f,out);hashes[f.name]=s.sha(f)
    assert len(allqs)==2000
    s.put(dest/"forecast-seal.json",dict(fit=s.sha(HERE/f"fit-{stage}.json"),forecasts=hashes,q=2000,t=1207))
if __name__=="__main__":
    {"fit":fit,"infer":infer}[sys.argv[1]](sys.argv[2])
