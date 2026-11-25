"""Train-only fine reader; all scoring and token packing reuse the unchanged dev study."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import gzip,json,os,sqlite3,sys
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):os.environ[k]="1"
D=Path(__file__).resolve().parent;OLD=D.parents[1]/"graph_memory_round19";G=D.parent/"residual_graph"
P=Path("D:/CodexResearch/x20-isetrace-fine-train");PROJ=Path("D:/CodexResearch/x20-isetrace-trained/projection/train")
sys.path.insert(0,str(D.parent/"fine_read"));import reader as rd
sys.path.insert(0,str(OLD.parent/"graph_memory_round18/isetrace_e5"))
from project import pilot
from forecasts import Lookup
from graph_memory.retrieval.methods.flat.dense import DenseTaskRetriever
from graph_memory.retrieval.requests import TextCandidate,TextRankingRequest
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from reader import load,save,sha
def extract(i):
    lock=load(D/"data-lock.json");name=f"inventory-{i}.json";assert sha(D/name)==lock["shards"][name]
    assert (G/"cost-ft.json").exists()
    db=sqlite3.connect(Path("D:/CodexResearch/x20-isetrace-residual/vectors.sqlite3").as_uri()+"?mode=ro",uri=True,timeout=120)
    ret=DenseTaskRetriever(encoder=Lookup(db,"ft"),device="cpu");xx=[];yy=[];qs=[]
    for t,h in sorted(load(D/name)["files"].items()):
        source=P/f"{i}-{t}.json.gz";assert sha(source)==h
        base=load(source);p=load(PROJ/(t+".json.gz"));raw={"fields":base["fields"],"pool":p["pool"]}
        candidates=tuple(TextCandidate.model_validate(x) for x in p["pool"]);geom=None
        for rec in p["qs"]:
            q=rec["q"];task=TextRankingRequest(task_id=q,query_text=rec["text"],candidates=candidates)
            rank=ret.rank(task);packed=pilot.assemble_ranked_result(request=task,method="dense",ranked_nodes=rank,top_k=len(rank),latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes
            rr=[v.model_dump() for v in packed]
            if geom is None:geom=rd.geometry(base,raw,rr)
            x,_,_=rd.features(rec["text"],rr,base["blocks"],geom)
            mask=np.array([bool(v) for v in geom[2]]);y=np.zeros(len(x),bool);y[base["targets"][q]]=1
            xx.append(x[mask]);yy.append(y[mask]);qs.append(q)
    xx=np.vstack(xx);yy=np.concatenate(yy);target=P/f"features-{i}.npz"
    np.savez_compressed(target,x=xx.astype(np.float32),y=yy);db.close()
    return {"n":len(yy),"positives":int(yy.sum()),"queries":qs,"sha":sha(target)}
def fit():
    with ProcessPoolExecutor(2) as executor:sh=list(executor.map(extract,range(8)))
    qset={q for row in sh for q in row["queries"]};assert len(qset)==sum(len(r["queries"]) for r in sh)==3894
    splits=load(OLD/"trained_rank/split.json.gz");assert qset=={r["q"] for r in splits["train"]}
    use=[np.load(P/f"features-{i}.npz") for i in range(8)]
    x=np.vstack([u["x"] for u in use]);y=np.concatenate([u["y"] for u in use]);models={}
    for name,columns in (("full",rd.FULL),("reduced",rd.RED)):
        z=x[:,columns].astype(np.float64);sc=StandardScaler(copy=False).fit(z);sc.transform(z)
        lr=LogisticRegression(C=1,class_weight="balanced",max_iter=2000,random_state=13).fit(z,y)
        models[name]={"columns":columns,"mean":sc.mean_.tolist(),"scale":sc.scale_.tolist(),"coef":lr.coef_[0].tolist(),"offset":float(lr.intercept_[0]),"iters":int(lr.n_iter_[0])}
    save(D/"model.json",{"questions":len(qset),"trajectories":len({r["t"] for r in splits["train"]}),"models":models,"rows":len(y),"positives":int(y.sum()),"features":rd.NAMES,"feature_shards":sh,"source":sha(G/"vectors-plan.json"),"reader":sha(rd.D/"reader.py"),"protocol":sha(D/"PROTOCOL_RU.md")})
def predict_shard(job):
    stage,i,folder=job;training=stage=="dev"
    rank=load(rd.source(stage,i));by=defaultdict(list)
    for rec in rank:by[rec["t"]].append(rec)
    cache=rd.DEV if training else rd.stream.CACHE
    model=load(folder/"model.json");out=[]
    with gzip.open(rd.blocks_path(stage,i),"rb") as f:
        for line in f:
            base=json.loads(line);t=base["t"];qs=by.pop(t,[])
            if not qs:
                assert training
                continue
            raw=load(cache/f"{i}-{t}.json.gz");ad,blocks=base["addresses"],base["blocks"]
            texts=dict(raw["q"]);geom=rd.geometry(base,raw,qs[0]["rr"]);used={};picks={}
            for r in qs:
                q=r["q"];x,rp,rl=rd.features(texts[q],r["rr"],blocks,geom)
                arms=rd.choose(r,blocks,geom,x,rp,rl,model);picks[q]=arms
                for group in arms.values():
                    for k in group:used[k]=blocks[int(k[6:])][:4] if k.startswith("micro/") else geom[0][k]
            out.append({"t":t,"addresses":ad,"used":used,"picks":picks})
    if not training:assert not by
    p=folder/f"{stage}-decisions-{i}.json.gz";save(p,out);return sha(p)
def predict(stage,folder=D):
    with ProcessPoolExecutor(3) as ex:checks=list(ex.map(predict_shard,[(stage,i,folder) for i in range(8)]))
    save(folder/(stage+"-forecast-seal.json"),{"model":sha(folder/"model.json"),"code":sha(D/"apply.py"),"reader":sha(rd.D/"reader.py"),"ranks":{rd.source(stage,i).name:sha(rd.source(stage,i)) for i in range(8)},
         "files":{f"{stage}-decisions-{i}.json.gz":h for i,h in enumerate(checks)}})
if __name__=="__main__":
    if sys.argv[1]=="fit":fit()
    else:predict(sys.argv[1])
