from __future__ import annotations
from pipeline import ROOT,IN, CACHE,writegz,loadgz,h,dump,key,select,slim,process
from features import pair_features
from direction import extra
import gzip,itertools,json,re,time
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier

def norm(s):return " ".join(s.casefold().split())
def fields(item):
    node,meta,bm,pairs,x,shuffle,e,count,ns=pair_features(item)
    role,placebo=extra(item,node,bm,pairs,e)
    r={"id":item[0],"titles":item[2],"n":len(pairs),"bm":bm,"edges":e,"directed_edges":count,"witnesses":ns}
    n=np.asarray([meta+p for p in node],np.float32)
    return r,n,np.array(x,np.float32),np.array(shuffle,np.float32),np.array(role,np.float32),np.array(placebo,np.float32)

def get():
    trains=set(json.loads((CACHE/"train_gold.json").read_text(encoding="utf-8")))
    train=[]; exclude=set()
    for batch in pq.ParquetFile(IN/"train-half.parquet").iter_batches(batch_size=512,columns=["id","question","context"]):
        for r in batch.to_pylist():
            if r["id"] in trains:
                train.append(slim(r));exclude.add(norm(r["question"]))
    exclude.update(norm(s) for s in pq.read_table(IN/"dev.parquet",columns=["question"])["question"].to_pylist())
    tr2=IN/"transfer-train-half.parquet"
    md=pq.read_table(tr2,columns=["id","question"]).to_pylist()
    eligible=[r["id"] for r in md if norm(r["question"]) not in exclude and r["id"] not in trains]
    selected=set(sorted(eligible,key=lambda u:key("external-hotpot-261118|"+u))[:2000])
    more=[]
    for batch in pq.ParquetFile(tr2).iter_batches(batch_size=512,columns=["id","question","context"]):
        more.extend(slim(r) for r in batch.to_pylist() if r["id"] in selected)
    mu=[]
    boundary=re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
    for line in (IN/"musique-dev.jsonl").open(encoding="utf-8"):
        r=json.loads(line)
        if not r["id"].startswith("2hop"):continue
        ps=r["paragraphs"];assert [p["idx"] for p in ps]==list(range(len(ps)))
        mu.append((r["id"],r["question"],[p["title"] for p in ps],[boundary.split(p["paragraph_text"]) for p in ps]))
    two=[]
    tab=pq.read_table(IN/"2wiki-dev.parquet",columns=["_id","question","type","context"]).to_pylist()
    choose=sorted((r for r in tab if r["type"]!="bridge_comparison"),key=lambda r:key("external-wiki-261118|"+r["_id"]))[:2000]
    for r in choose:
        docs=json.loads(r["context"])
        two.append((r["_id"],r["question"],[item[0] for item in docs],[item[1] for item in docs]))
    assert len(train)==6000 and len(more)==2000 and len(mu)==1252 and len(two)==2000
    return {d:sorted(rows,key=lambda r:r[0]) for d,rows in (("train",train),("h2",more),("mu",mu),("w2",two))}
def fit(X,y):
    m=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,learning_rate=.1,min_samples_leaf=30,l2_regularization=1,
                                     random_state=261118,early_stopping=False)
    return m.fit(X,y)
def matrix(data,model):
    n,x,sh,r,r0=data
    if model=="point":return n
    if model=="flat":return x[:,:34]
    if model=="graph":return x[:,:42]
    if model=="origin":return x
    if model=="shuffle":return np.concatenate((x[:,:42],sh),axis=1)
    if model=="roles":return np.concatenate((x[:,:42],r[:,:18]),axis=1)
    if model=="compete":return np.concatenate((x[:,:42],r),axis=1)
    if model=="reversed":return np.concatenate((x[:,:42],r0),axis=1)
    raise KeyError(model)
def learn():
    start=time.perf_counter()
    cohorts=get(); dataset={};meta={}
    for name,records in cohorts.items():
        fields1=[];ns=[];xx=[];sh=[];rs=[];rr=[]
        with ProcessPoolExecutor(max_workers=3) as pool:
            for row,n,x,w,r,r0 in pool.map(fields,records,chunksize=12):
                fields1.append(row);ns.append(n);xx.append(x);sh.append(w);rs.append(r);rr.append(r0)
        print("features",name,len(fields1),round(time.perf_counter()-start,1),flush=True)
        dataset[name]=[np.concatenate(z) for z in (ns,xx,sh,rs,rr)]
        meta[name]=fields1
    oldmeta=loadgz(CACHE/"train_meta.jsonl.gz");assert [r["id"] for r in oldmeta]==[r["id"] for r in meta["train"]]
    assert np.array_equal(dataset["train"][0],np.load(CACHE/"train_node.npy"))
    assert np.array_equal(dataset["train"][1],np.load(CACHE/"train_x.npy"))
    assert np.array_equal(dataset["train"][2],np.load(CACHE/"train_sh.npy"))
    g=json.loads((CACHE/"train_gold.json").read_text(encoding="utf-8"))
    yn=[];yp=[]
    for row in meta["train"]:
        gt=set(g[row["id"]]);t=row["titles"]
        yn.extend(v in gt for v in t)
        yp.extend(set(p)==gt for p in itertools.combinations(t,2))
    gold_node=np.array(yn,np.int8);gold_pair=np.array(yp,np.int8)
    beams={name:json.loads((IN/(src+"-beam.json")).read_text(encoding="utf-8")) for name,src in (("mu","musique"),("w2","2wiki"))}
    models=["point","flat","graph","origin","shuffle","roles","compete","reversed"]; totals={}
    scores={n:{} for n in cohorts if n!="train"}
    for model in models:
        t=time.perf_counter();mm=fit(matrix(dataset["train"],model),gold_node if model=="point" else gold_pair)
        for name in scores:scores[name][model]=mm.decision_function(matrix(dataset[name],model))
        totals[model]=time.perf_counter()-t;print("transfer fit",model,round(totals[model],1),flush=True)
    expected=json.loads((ROOT/"prediction_lock.json").read_text(encoding="utf-8"))["curves"]
    out=[]
    for name in scores:
        ptr=0;pn=0
        for row in meta[name]:
            uid=row["id"]; tt=row["titles"]; n=len(tt);pairs=list(itertools.combinations(range(n),2))
            ties=[key("|".join((uid,*sorted([tt[i],tt[j]])))) for i,j in pairs]
            ntie=[key(uid+"|"+z) for z in tt]
            pred={};support={}
            for model in ("bm","point"):
                z=row["bm"] if model=="bm" else scores[name]["point"][pn:pn+n]
                pred[model]=sorted(sorted(range(n),key=lambda i:(z[i],ntie[i]),reverse=True)[:2])
            for model in models[1:]:
                z=scores[name][model][ptr:ptr+len(pairs)]
                idx=select(z,range(len(pairs)),ties)
                pred[model]=list(pairs[idx])
                if model in ("origin","roles","compete"): support[model]=row["edges"][idx]
                if name in beams and model in ("origin","graph"):
                    native=sorted(beams[name][uid])
                    assert len(native)==len(set(native))==2 and min(native)>=0 and max(native)<n,(name,uid,native)
                    bidx=pairs.index(tuple(native));th=expected[model]["threshold"]
                    pred["beam_"+model]=pred[model] if th!="never" and z[idx]-z[bidx]>th else native
            if name in beams:pred["beam"]=sorted(beams[name][uid])
            out.append({"dataset":name,"id":uid,"titles":tt,"group":tt[max(range(n),key=lambda i:(row["bm"][i],ntie[i]))].casefold(),
                        "pred":pred,"witness_positions":support})
            pn+=n;ptr+=len(pairs)
    writegz(out,ROOT/"transfer_predictions.jsonl.gz")
    dump({"prediction_sha256":h(ROOT/"transfer_predictions.jsonl.gz"),"input_sha256":{p.name:h(p) for p in IN.iterdir() if p.is_file()},
          "source_sha256":{p.name:h(p) for p in ROOT.glob("*.py")},"seconds_total":time.perf_counter()-start,
          "seconds_fit":totals,"same_training_features_bitwise":True,"counts":{n:len(r) for n,r in meta.items()},
          "preregistration_sha":{p.name:h(p) for p in ROOT.glob("*PROTOCOL.md")}},"transfer_lock.json")
def grade():
    rows=loadgz(ROOT/"transfer_predictions.jsonl.gz")
    assert h(ROOT/"transfer_predictions.jsonl.gz")==json.loads((ROOT/"transfer_lock.json").read_text(encoding="utf-8"))["prediction_sha256"]
    roster={r["id"] for r in rows}
    gt={}
    for batch in pq.ParquetFile(IN/"transfer-train-half.parquet").iter_batches(batch_size=512,columns=["id","supporting_facts"]):
        for r in batch.to_pylist():
            if r["id"] in roster:gt["h2",r["id"]]=set(r["supporting_facts"]["title"])
    for r in pq.read_table(IN/"2wiki-dev.parquet",columns=["_id","supporting_facts"]).to_pylist():
        if r["_id"] in roster:gt["w2",r["_id"]]={t for t,i in json.loads(r["supporting_facts"])}
    for line in (IN/"musique-dev.jsonl").open(encoding="utf-8"):
        r=json.loads(line)
        if r["id"] in roster:gt["mu",r["id"]]={x["idx"] for x in r["paragraphs"] if x["is_supporting"]}
    outcomes=[]
    for r in rows:
        key0=(r["dataset"],r["id"]);truth=gt[key0]
        chosen={a:(set(v) if key0[0]=="mu" else {r["titles"][i] for i in v}) for a,v in r["pred"].items()}
        outcomes.append({"dataset":key0[0],"id":key0[1],"group":r["group"],"n_gold":len(truth),"hits":{a:int(v==truth) for a,v in chosen.items()},
                         "recall":{a:len(v&truth)/len(truth) for a,v in chosen.items()}})
    results={}
    for name in ("h2","mu","w2"):
        rr=[r for r in outcomes if r["dataset"]==name]
        n=len(rr);arms=list(rr[0]["hits"])
        pairs=[("compete","roles"),("roles","graph"),("roles","reversed"),("compete","graph"),("origin","graph"),("origin","shuffle"),("graph","flat")]
        if name!="h2":pairs.extend([("compete","beam"),("beam_origin","beam")])
        comp={}
        for a,b in pairs:
            d=np.array([r["hits"][a]-r["hits"][b] for r in rr],dtype=np.int8)
            grp,ix=np.unique([r["group"] for r in rr],return_inverse=True)
            sums=np.bincount(ix,weights=d);counts=np.bincount(ix);rng=np.random.default_rng(261118);arr=[]
            for _ in range(100):
                sample=rng.integers(len(grp),size=(100,len(grp)));arr.append(sums[sample].sum(1)/counts[sample].sum(1))
            from scipy.stats import binomtest
            w=int((d>0).sum());l=int((d<0).sum())
            comp[a+"-"+b]={"delta":float(d.mean()),"wins":w,"losses":l,"ties":n-l-w,"cluster_n":len(grp),
                           "ci":np.quantile(np.concatenate(arr),[.025,.975]).tolist(),"p":float(binomtest(w,w+l,.5).pvalue) if w+l else 1.}
        results[name]={"n":n,"gold_sizes":dict(Counter(r["n_gold"] for r in rr)),"hits":{a:sum(r["hits"][a] for r in rr) for a in arms},
                 "mean_recall":{a:float(np.mean([r["recall"][a] for r in rr])) for a in arms},"contrasts":comp}
        print("test",name,n,results[name]["hits"],flush=True)
    writegz(outcomes,ROOT/"transfer_item_scores.jsonl.gz")
    dump(results,"transfer_results.json")
if __name__=="__main__":
    import sys
    if sys.argv[1] in ("all","learn"):learn()
    if sys.argv[1] in ("all","grade"):grade()

