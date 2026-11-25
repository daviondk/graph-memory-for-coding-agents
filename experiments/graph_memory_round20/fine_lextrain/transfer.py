"""Learn on query-local BM25 parent ranks and transfer the frozen estimator to dense ranks."""
from pathlib import Path
import sys
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"fine_train"))
import apply as app
from apply import rd,np,save,load,sha,StandardScaler,LogisticRegression,ProcessPoolExecutor,TextCandidate,TextRankingRequest,pilot
from graph_memory.retrieval.methods.flat.bm25 import BM25TaskRetriever
def extract(i):
    inventory=load(app.D/f"inventory-{i}.json");ret=BM25TaskRetriever();xx=[];yy=[];qs=[]
    for t,h in sorted(inventory["files"].items()):
        src=app.P/f"{i}-{t}.json.gz";assert sha(src)==h
        base=load(src);p=load(app.PROJ/(t+".json.gz"));raw={"fields":base["fields"],"pool":p["pool"]}
        candidates=tuple(TextCandidate.model_validate(x) for x in p["pool"]);geom=None
        for rec in p["qs"]:
            q=rec["q"];req=TextRankingRequest(task_id=q,query_text=rec["text"],candidates=candidates)
            rank=ret.rank(req);packed=pilot.assemble_ranked_result(request=req,method="bm25",ranked_nodes=rank,top_k=len(rank),latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes
            rr=[v.model_dump() for v in packed]
            if geom is None:geom=rd.geometry(base,raw,rr)
            x,_,_=rd.features(rec["text"],rr,base["blocks"],geom)
            mask=np.asarray([bool(v) for v in geom[2]]);y=np.zeros(len(x),bool);y[base["targets"][q]]=1
            xx.append(x[mask]);yy.append(y[mask]);qs.append(q)
    target=app.P/f"lexical-features-{i}.npz";np.savez_compressed(target,x=np.vstack(xx).astype(np.float32),y=np.concatenate(yy))
    return {"queries":qs,"sha":sha(target)}
def fit():
    with ProcessPoolExecutor(2) as pool:sh=list(pool.map(extract,range(8)))
    qs={a for r in sh for a in r["queries"]};split=load(app.OLD/"trained_rank/split.json.gz")["train"]
    assert qs=={r["q"] for r in split} and sum(len(r["queries"]) for r in sh)==3894
    parts=[np.load(app.P/f"lexical-features-{i}.npz") for i in range(8)]
    x=np.vstack([u["x"] for u in parts]);y=np.concatenate([u["y"] for u in parts]);models={}
    for name,cols in (("full",rd.FULL),("reduced",rd.RED)):
        z=x[:,cols].astype(np.float64);sc=StandardScaler(copy=False).fit(z);sc.transform(z)
        lr=LogisticRegression(C=1,class_weight="balanced",max_iter=2000,random_state=13).fit(z,y)
        models[name]={"columns":cols,"mean":sc.mean_.tolist(),"scale":sc.scale_.tolist(),"coef":lr.coef_[0].tolist(),"offset":float(lr.intercept_[0]),"iters":int(lr.n_iter_[0])}
    save(D/"model.json",{"questions":len(qs),"trajectories":len({r["t"] for r in split}),"rows":len(y),"positives":int(y.sum()),"models":models,
                        "features":rd.NAMES,"shards":sh,"data":sha(app.D/"data-lock.json"),"code":sha(D/"transfer.py"),"protocol":sha(D/"PROTOCOL_RU.md"),"reader":sha(rd.D/"reader.py")})
if __name__=="__main__":
    if sys.argv[1]=="fit":fit()
    else:app.predict(sys.argv[1],D)
