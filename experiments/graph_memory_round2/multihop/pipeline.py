from __future__ import annotations
import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]:
    os.environ[k]="2"
import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip, hashlib, itertools, json, platform, sys, time
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
import pyarrow.dataset as ds
from sklearn import __version__ as sklearn_version
from sklearn.ensemble import HistGradientBoostingClassifier
from features import pair_features,key

ROOT=Path(__file__).resolve().parent
IN=ROOT/"inputs"
CACHE=ROOT/"cache"
CACHE.mkdir(exist_ok=True)
def dump(obj,name):
    (ROOT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
def h(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def writegz(rows,path):
    with gzip.GzipFile(filename=str(path),mtime=0,mode="wb",compresslevel=6) as f:
        for row in rows:f.write((json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8"))
def loadgz(path):
    with gzip.open(path,"rt",encoding="utf-8") as f:return [json.loads(x) for x in f]
def process(item):
    uid,question,titles,sents=item
    node,meta,bm,pairs,X,W,sp,e,c=pair_features(item)
    ins=uid.endswith("02") # choose ~1/256 independent of truth; no predictions used.
    if ins:
        r=pair_features(item,list(reversed(range(len(titles)))))
        assert np.array_equal(r[4],X) and np.array_equal(r[5],W) and sp==r[6]
    data={"id":uid,"titles":titles,"npairs":len(pairs),"bm":bm,"links":sp,"nedges":e,"witnesses":c,
          "permutation_checked":ins}
    return data,np.asarray([meta+a for a in node],np.float32),np.asarray(X,np.float32),np.asarray(W,np.float32)
def dev_split(ids):
    sorted_ids=sorted(ids,key=lambda i:key("calibration-261118|"+i))
    return set(sorted_ids[:2000])
def slim(r):return (r["id"],r["question"],r["context"]["title"],r["context"]["sentences"])
def project():
    t=time.perf_counter()
    devpath=IN/"dev.parquet";trainpath=IN/"train-half.parquet"
    dev=pq.read_table(devpath,columns=["id","question","context"]).to_pylist()
    norm=lambda s:" ".join(s.lower().split())
    seen={norm(r["question"]) for r in dev}
    tmeta=pq.read_table(trainpath,columns=["id","question"]).to_pylist()
    eligible=[r for r in tmeta if norm(r["question"]) not in seen]
    allowed=set(r["id"] for r in sorted(eligible,key=lambda x:key("train-261118|"+x["id"]))[:6000])
    train=[]
    for batch in pq.ParquetFile(trainpath).iter_batches(batch_size=256,columns=["id","question","context","supporting_facts"]):
        train.extend(r for r in batch.to_pylist() if r["id"] in allowed)
    assert len(train)==6000 and not allowed & {r["id"] for r in dev}
    trlabels={r["id"]:r["supporting_facts"]["title"] for r in train}
    dump(trlabels,"cache/train_gold.json")
    stage={}
    for name,rows in [("train",train),("dev",dev)]:
        rows=sorted(rows,key=lambda r:r["id"])
        results=[]; nodes=[];xx=[]; ww=[]
        with ProcessPoolExecutor(max_workers=3) as ex:
            for idx,(d,node,x,w) in enumerate(ex.map(process,map(slim,rows),chunksize=12)):
                results.append(d);nodes.append(node);xx.append(x);ww.append(w)
                if (idx+1)%1500==0: print(name,idx+1,round(time.perf_counter()-t,1),flush=True)
        allnode=np.concatenate(nodes);allx=np.concatenate(xx);sh=np.concatenate(ww)
        assert allx.shape[1]==34+8+14
        assert allnode.shape[1]==18
        np.save(CACHE/(name+"_node.npy"),allnode)
        np.save(CACHE/(name+"_x.npy"),allx)
        np.save(CACHE/(name+"_sh.npy"),sh)
        writegz(results,CACHE/(name+"_meta.jsonl.gz"))
        stage[name]={"n":len(rows),"pairs":len(allx),"nodes":len(allnode),"edges":sum(x["nedges"] for x in results),
                     "witnesses":sum(x["witnesses"] for x in results),"reverse_order_exact":sum(r["permutation_checked"] for r in results)}
    dump({"stage":stage,"exact_question_duplicates_removed":len(tmeta)-len(eligible),"cpu_seconds_wall":time.perf_counter()-t,
          "python":sys.version,"platform":platform.platform(),"numpy":np.__version__,"sklearn":sklearn_version,
          "input_sha256":{p.name:h(p) for p in IN.iterdir() if p.is_file()},
          "code_sha256":{p.name:h(p) for p in ROOT.glob("*.py")}},"feature_receipt.json")

def train(name, f, y, fd):
    spec=HistGradientBoostingClassifier(learning_rate=.1,max_iter=100,max_leaf_nodes=15,l2_regularization=1,
          min_samples_leaf=30,early_stopping=False,random_state=261118)
    t=time.perf_counter()
    spec.fit(f,y)
    scores=spec.decision_function(fd)
    assert np.isfinite(scores).all()
    np.save(CACHE/(name+"_scores.npy"),scores)
    print("fit",name,len(y),round(time.perf_counter()-t,2),flush=True)
    return scores
def goldrows(qids):
    table=ds.dataset(IN/"dev.parquet",format="parquet").to_table(columns=["id","supporting_facts"],
                      filter=ds.field("id").isin(list(qids)))
    return {r["id"]:set(r["supporting_facts"]["title"]) for r in table.to_pylist()}
def select(raw,indices,ties):
    # lexical order is a fixed random per-question tie-break shared across all arms.
    ind=max(indices,key=lambda i:(raw[i],ties[i]))
    return ind
def fit():
    t=time.perf_counter()
    tr=loadgz(CACHE/"train_meta.jsonl.gz"); dv=loadgz(CACHE/"dev_meta.jsonl.gz")
    g=json.loads((CACHE/"train_gold.json").read_text(encoding="utf-8"));nodegold=[];pairgold=[]
    for r in tr:
        gt=set(g[r["id"]]);tt=r["titles"]
        nodegold.extend(a in gt for a in tt)
        pairgold.extend({tt[i],tt[j]}==gt for i,j in itertools.combinations(range(len(tt)),2))
    x=np.load(CACHE/"train_x.npy",mmap_mode='r');xd=np.load(CACHE/"dev_x.npy",mmap_mode='r')
    yy=np.asarray(pairgold,dtype=np.int8)
    s={}
    s["point"]=train("point",np.load(CACHE/"train_node.npy"),np.asarray(nodegold,dtype=np.int8),np.load(CACHE/"dev_node.npy"))
    for a,k in [("flat",34),("graph",42),("origin",56)]:
        s[a]=train(a,x[:,:k],yy,xd[:,:k])
    def with_shuffle(x,name):
        return np.column_stack((x[:,:42],np.load(CACHE/(name+"_sh.npy"))))
    s["shuffle"]=train("shuffle",with_shuffle(x,"train"),yy,with_shuffle(xd,"dev"))
    native=json.loads((IN/"beam.json").read_text(encoding="utf-8"))
    out=[];ns=0; ps=0
    for r in dv:
        uid=r["id"];tt=r["titles"];n=len(tt);pairs=list(itertools.combinations(range(n),2))
        ties=[key("|".join((uid,*sorted([tt[i],tt[j]])))) for i,j in pairs]
        pred={}
        def nodes(ids):return sorted(ids)
        rankties=[key(uid+"|"+z) for z in tt]
        for a,values in [("bm",r["bm"]),("point",s["point"][ns:ns+n])]:
            pred[a]=nodes(sorted(range(n),key=lambda i:(values[i],rankties[i]),reverse=True)[:2])
        b=sorted(native[uid])
        assert len(b)==2 and len(set(b))==2 and b[0]>=0 and b[1]<n
        pred["beam"]=b
        margin={};ev={}
        bi=pairs.index(tuple(b))
        for a in ["flat","graph","origin","shuffle"]:
            scores=s[a][ps:ps+len(pairs)]
            at=select(scores,range(len(pairs)),ties)
            pred[a]=list(pairs[at]);margin[a]=float(scores[at]-scores[bi])
            if a in {"origin","graph"}:ev[a]=r["links"][at]
        group=tt[max(range(n),key=lambda i:(r["bm"][i],rankties[i]))].casefold()
        out.append(dict(id=uid,titles=tt,group=group,pred=pred,margin=margin,edge_evidence=ev))
        ns+=n;ps+=len(pairs)
    common=set(r["id"] for r in out);assert len(common)==len(native)==7405
    cal=dev_split(common)
    gc=goldrows(cal)
    assert set(gc)==cal
    grids={}
    for a in ("graph","origin"):
        grid=[]
        for threshold in [0,1,2,3,4,5,6,mathinf()]:
            switches=hits=0
            for r in out:
                if r["id"] not in cal:continue
                switch=r["margin"][a]>threshold; chosen=r["pred"][a if switch else "beam"]
                switches+=switch
                hits+=({r["titles"][i] for i in chosen}==gc[r["id"]])
            grid.append((hits,-switches,threshold))
        h0,ms,threshold=max(grid)
        grids[a]={"threshold":threshold if np.isfinite(threshold) else "never",
                  "cal": [[h,-m,z if np.isfinite(z) else "never"] for h,m,z in grid]}
        for r in out:
            switch=r["margin"][a]>threshold
            r["pred"]["beam_"+a]=r["pred"][a if switch else "beam"]
    for r in out:r["split"]="cal" if r["id"] in cal else "test"
    writegz(out,ROOT/"predictions.jsonl.gz")
    dump({"sha256":h(ROOT/"predictions.jsonl.gz"),"curves":grids,"seconds":time.perf_counter()-t,
          "ntrain":len(tr),"model_inputs":"no answer, support, type or level, no pretrained evidence reader apart from the published frozen Beam outputs",
          "fit_pair_positive_fraction":float(yy.mean()),"feature_receipt_sha":h(ROOT/"feature_receipt.json")},"prediction_lock.json")
def mathinf():return float("inf")

def assess():
    lock=json.loads((ROOT/"prediction_lock.json").read_text(encoding="utf-8"))
    assert lock["sha256"]==h(ROOT/"predictions.jsonl.gz")
    rows=loadgz(ROOT/"predictions.jsonl.gz")
    gold=goldrows({r["id"] for r in rows})
    types={r["id"]:r["type"] for r in pq.read_table(IN/"dev.parquet",columns=["id","type"]).to_pylist()}
    per=[]; keys=list(rows[0]["pred"])
    for r in rows:
        gt=gold[r["id"]]
        ev={a:({r["titles"][i] for i in inds}) for a,inds in r["pred"].items()}
        per.append({"id":r["id"],"split":r["split"],"group":r["group"],"type":types[r["id"]],
                    "hits":{a:int(p==gt) for a,p in ev.items()},
                    "recalls":{a:len(p & gt)/len(gt) if gt else 0 for a,p in ev.items()},
                    "gold_indices":[i for i,t in enumerate(r["titles"]) if t in gt],
                    "changes":{a:int(set(r["pred"][a])!=set(r["pred"]["beam"])) for a in keys}})
    writegz(per,ROOT/"scores_per_item.jsonl.gz")
    def analyze(rr):
        n=len(rr)
        totals={a:{"hits":sum(r["hits"][a] for r in rr),"recall":float(np.mean([r["recalls"][a] for r in rr])),
                   "different_from_beam":sum(r["changes"][a] for r in rr)} for a in keys}
        comps={}
        for a,b in [("origin","graph"),("origin","flat"),("origin","shuffle"),("graph","flat"),("flat","point"),
                    ("beam_origin","beam"),("beam_graph","beam"),("beam_origin","beam_graph"),("origin","beam")]:
            d=np.array([r["hits"][a]-r["hits"][b] for r in rr],np.int16)
            groups,ix=np.unique([r["group"] for r in rr],return_inverse=True)
            sums=np.bincount(ix,weights=d);cnt=np.bincount(ix)
            rng=np.random.default_rng(261118); parts=[]
            for _ in range(100):
                samp=rng.integers(len(groups),size=(100,len(groups)))
                parts.append(sums[samp].sum(1)/cnt[samp].sum(1))
            ci=np.quantile(np.concatenate(parts),[.025,.975]).tolist()
            w=int((d>0).sum()); l=int((d<0).sum())
            from scipy.stats import binomtest
            p=float(binomtest(w,w+l,.5).pvalue) if w+l else 1.
            comps[a+"-"+b]={"delta":float(d.mean()),"wins":w,"losses":l,"ties":n-w-l,"clusters":len(groups),
                              "cluster_percentile_95":ci,"exact_mcnemar_descriptive":p}
        return {"n":n,"totals":totals,"contrasts":comps}
    out={}
    for group,ss in [("cal",[r for r in per if r["split"]=="cal"]),
                     ("test",[r for r in per if r["split"]=="test"]),("all",per)]:
        out[group]=analyze(ss)
    st=[r for r in per if r["split"]=="test"]
    for typ in sorted(set(types.values())):
        sub=[r for r in st if r["type"]==typ]
        out["test_"+typ]={"n":len(sub),"totals":{a:sum(r["hits"][a] for r in sub) for a in keys}}
    out["truth_counts"]={str(k):sum(len(g)==k for g in gold.values()) for k in sorted(set(map(len,gold.values())))}
    dump(out,"results.json")
    print("test",out["test"]["n"],{k:v["hits"] for k,v in out["test"]["totals"].items()})
    print(out["test"]["contrasts"]["origin-graph"],out["test"]["contrasts"]["beam_origin-beam"])
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("stage",choices=["project","fit","assess","all"]);a=parser.parse_args()
    if a.stage in ("project","all"):project()
    if a.stage in ("fit","all"):fit()
    if a.stage in ("assess","all"):assess()


