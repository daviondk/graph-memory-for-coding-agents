"""Combine an original-train structural prior and a disjoint small-sample semantic rank calibration."""
from pathlib import Path
import sys,os
for n in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[n]="1"
D=Path(__file__).resolve().parent;ROOT=D.parent
sys.path.insert(0,str(ROOT/"fine_train"));import apply as app
from apply import np,save,load,sha,StandardScaler,LogisticRegression,DenseTaskRetriever,Lookup,TextCandidate,TextRankingRequest
import importlib.util
spec=importlib.util.spec_from_file_location("typed_graph_source",ROOT/"typed_reader/study.py");gmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(gmod)
import sqlite3,hashlib
from collections import defaultdict,Counter
from concurrent.futures import ProcessPoolExecutor
P=app.P/"node-priors";P.mkdir(exist_ok=True)
SHAPE=["output","log_tokens","log_chunk","relative_chunk","first","last","log_event_chunks"]
DEG=["deg"+str(i) for i in range(8)]
def shape(candidates,graph):
    ids,real,_,_,_=graph;n=len(ids)
    ds=np.column_stack([np.log1p(np.bincount(dest,minlength=n)) for dest,orig in real])
    events=Counter(p["source_spans"][0]["event_id"] for p in candidates);lookup={p["item_id"]:p for p in candidates}
    assert set(lookup)==set(ids)
    order=sorted(ids,key=ids.get);rows=[]
    for j,k in enumerate(order):
        p=lookup[k];m=p["metadata"];event=p["source_spans"][0]["event_id"];size=events[event];pos=m["chunk_index"]
        rows.append([int(m["node_kind"]=="content.tool_output"),np.log1p(m["token_count"]),np.log1p(pos),pos/max(1,size-1),int(pos==0),int(pos==size-1),np.log1p(size),*ds[j]])
    return order,np.asarray(rows)
def labels(ordered,gold):
    y=np.asarray([k in gold for k in ordered]);n1=int(y.sum());n0=len(y)-n1
    assert n1>0
    if not n0:return None
    return y,np.where(y,.5/n1,.5/n0)
def prepare(i):
    index=gmod.graph_index();spl=load(app.OLD/"trained_rank/split.json.gz")["train"];co=load(app.G/"cpu_fallback/cohorts.json")
    exclude=set(t for v in co.values() for t in v["t"]);want={r["t"] for r in spl}-exclude
    ids=load(app.D/f"inventory-{i}.json")["files"];xs=[];ys=[];ws=[];queries=[];sel=[]
    for t in sorted(want.intersection(ids)):
        p=load(app.PROJ/(t+".json.gz"));ordered,x=shape(p["pool"],gmod.project(t,index))
        for q in p["qs"]:
            lab=labels(ordered,set(q["positive"]))
            if lab is None:continue
            y,w=lab;xs.append(x);ys.append(y);ws.append(w);queries.append(q["q"])
        sel.append(t)
    z=P/f"prior-{i}.npz";np.savez_compressed(z,x=np.vstack(xs),y=np.concatenate(ys),w=np.concatenate(ws))
    return {"file":sha(z),"q":queries,"t":sel}
def lr(x,y,w):
    w=w*len(y)/w.sum();sc=StandardScaler().fit(x,sample_weight=w);clf=LogisticRegression(C=1,max_iter=1000,random_state=13).fit(sc.transform(x),y,sample_weight=w);assert clf.n_iter_[0]<1000
    return {"coef":(clf.coef_[0]/sc.scale_).tolist(),"intercept":float(clf.intercept_[0]-(clf.coef_[0]/sc.scale_)@sc.mean_)}
def prior():
    with ProcessPoolExecutor(2) as ex: parts=list(ex.map(prepare,range(8)))
    keys=SHAPE+DEG;a=[np.load(P/f"prior-{i}.npz") for i in range(8)]
    x=np.vstack([r["x"] for r in a]);y=np.concatenate([r["y"] for r in a]);w=np.concatenate([r["w"] for r in a]);models={}
    for name,cols in {"prior":list(range(len(keys))),"shape":list(range(len(SHAPE))),"degree":list(range(len(SHAPE),len(keys)))}.items():
        models[name]={**lr(x[:,cols],y,w),"columns":cols}
    save(D/"prior.json",{"models":models,"features":keys,"train_rows":len(y),"positive":int(y.sum()),"inventory":parts,"train_questions":sum(len(p["q"]) for p in parts),"train_trajectories":sum(len(p["t"]) for p in parts),"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(D/"factor.py")})
def rank_x(n):
    r=np.arange(1,n+1);return np.column_stack((-np.log(r),1/r,(n-r)/max(1,n-1)))
def calibrate(cohort):
    record=load(app.G/"cpu_fallback/cohorts.json")[cohort];ts=set(record["t"]);index=gmod.graph_index()
    pri=load(D/"prior.json");prior_t={t for row in pri["inventory"] for t in row["t"]};assert not (ts & prior_t)
    db=sqlite3.connect(Path("D:/CodexResearch/x20-isetrace-residual/vectors.sqlite3").as_uri()+"?mode=ro",uri=True,timeout=120);ret=DenseTaskRetriever(encoder=Lookup(db,"ft"),device="cpu")
    ranks=[];shapes=[];ys=[];ws=[];ids=[]
    for t in sorted(ts):
        p=load(app.PROJ/(t+".json.gz"));sortedids,struct=shape(p["pool"],gmod.project(t,index));at={k:j for j,k in enumerate(sortedids)};c=tuple(TextCandidate.model_validate(v) for v in p["pool"])
        for q in p["qs"]:
            req=TextRankingRequest(task_id=q["q"],query_text=q["text"],candidates=c);ordered=[u.node_id for u in ret.rank(req)]
            lab=labels(ordered,set(q["positive"]))
            if lab is None:continue
            y,w=lab;ranks.append(rank_x(len(y)));shapes.append(struct[[at[k] for k in ordered]]);ys.append(y);ws.append(w);ids.append(q["q"])
    x=np.vstack(ranks);z=np.vstack(shapes);y=np.concatenate(ys);w=np.concatenate(ws)
    save(D/(cohort+"-weights.json"),{"rank":lr(x,y,w),"joint":lr(np.column_stack((x,z)),y,w),"queries":ids,"rows":len(y),"trajectories":len(ts),"prior":sha(D/"prior.json"),"cohort":sha(app.G/"cpu_fallback/cohorts.json")})
def lin(m,x):return x@np.array(m["coef"])+m["intercept"]
def forecast(job):
    cohort,i=job;pri=load(D/"prior.json")["models"];models=load(D/(cohort+"-weights.json"));index=gmod.graph_index();by=defaultdict(list)
    path=app.OLD/"trained_rank"/f"forecasts-main-{i}.json.gz"
    for r in load(path):by[r["t"]].append(r)
    out=[]
    for t,rows in by.items():
        base=load(app.rd.stream.CACHE/f"{i}-{t}.json.gz");keys,struct=shape(base["pool"],gmod.project(t,index));at={k:j for j,k in enumerate(keys)}
        for r in rows:
            rr=r["rr"];ids=[v["node_id"] for v in rr];order=[at[k] for k in ids];z=struct[order];rank=rank_x(len(rr));signal=lin(models["rank"],rank)
            allp={a:lin(m,z[:,m["columns"]]) for a,m in pri.items()};mis=allp["prior"].copy()
            for role in (0,1):
                inds=sorted(np.where(z[:,0]==role)[0],key=lambda j:hashlib.sha256((t+"|"+ids[j]).encode()).digest())
                if inds:mis[inds]=allp["prior"][np.roll(inds,len(inds)//2)]
            scores={"dense":-np.arange(len(rr)),"rank":signal,"shape":signal+allp["shape"],"degree":signal+allp["degree"],"factor":signal+allp["prior"],"sham":signal+mis,"joint":lin(models["joint"],np.column_stack((rank,z)))}
            out.append({"q":r["q"],"t":t,"ranks":{a:np.argsort(-s,kind="stable").tolist() for a,s in scores.items()}})
    target=D/f"{cohort}-ranks-{i}.json.gz";save(target,out);return sha(target)
def predict(cohort):
    with ProcessPoolExecutor(2) as ex: hashes=list(ex.map(forecast,[(cohort,i) for i in range(8)]))
    save(D/(cohort+"-seal.json"),{"files":{f"{cohort}-ranks-{i}.json.gz":h for i,h in enumerate(hashes)},"weights":sha(D/(cohort+"-weights.json")),"prior":sha(D/"prior.json"),"code":sha(D/"factor.py")})
if __name__=="__main__":
    if sys.argv[1]=="prior":prior()
    elif sys.argv[1]=="calibrate":calibrate(sys.argv[2])
    else:predict(sys.argv[2])
