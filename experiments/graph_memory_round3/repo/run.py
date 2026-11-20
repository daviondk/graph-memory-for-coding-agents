"""Feature, fit, predict and label phases are separate. Test-feature readers omit the test label and target."""
import os
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):
    os.environ[key]="1"
import argparse, collections, concurrent.futures, gzip, hashlib, json, pickle, time
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier
from io_utils import D, save, read, sha, dump, load_gz, now, np
from features import compute, BASE, OWN, EDGE
ARMS={"flat":(120,list(range(BASE))),"owner":(120,list(range(BASE+OWN))),"transition":(120,list(range(BASE+OWN+EDGE))),
      "placebo":(120,[*range(BASE+OWN),*range(BASE+OWN+EDGE,BASE+OWN+2*EDGE)]),
      "flat3":(3,list(range(BASE))),"transition3":(3,list(range(BASE+OWN+EDGE)))}
def panels():
    return sorted((D/"inputs").glob("*.parquet"))
def roster():
    test=set()
    for p in panels():
        if "_test_" in p.name:test.update(pq.read_table(p,columns=["repo_name"]).column(0).to_pylist())
    keep={}
    for p in panels():
        if "_train_" not in p.name:continue
        repos=pq.read_table(p,columns=["repo_name"]).column(0).to_pylist()
        cand=sorted(range(len(repos)),key=lambda j:hashlib.sha256(f"r3repo|{p.name}|{j}".encode()).hexdigest())
        picked=[];counts=collections.Counter()
        for j in cand:
            r=repos[j]
            if r in test or counts[r]>=25:continue
            picked.append(j);counts[r]+=1
            if len(picked)>=3000:break
        keep[p.stem]=sorted(picked)
    save("roster.json",keep)
    files=["PROTOCOL_RU.md","features.py","run.py","io_utils.py","sources.json","roster.json","inputs/codegen_tokenizer.json"]
    save("method_lock.json",{"utc":now(),"sha256":{s:sha(D/s) for s in files},"test_repos":len(test)})
def extract(p):
    start=time.time();train="_train_" in p.name
    selected=set(read("roster.json").get(p.stem,[]))
    cols=["repo_name","file_path","context","code"]+(["gold_snippet_index"] if train else [])
    dst=D/"cache";dst.mkdir(exist_ok=True);meta=[];arrays=[];small=[];offset=[0];idx=-1
    for batch in pq.ParquetFile(p).iter_batches(batch_size=32,columns=cols):
        for o in batch.to_pylist():
            idx+=1
            if train and idx not in selected:continue
            contexts=o["context"];code=o["code"]
            qh=hashlib.sha256(code.encode()).hexdigest()
            row=[idx,o["repo_name"],qh,len(contexts),[len(c) for c in contexts]]
            if train:row.append(o['gold_snippet_index'])
            meta.append(row);f=compute(code,contexts,120);short=compute(code,contexts,3)
            assert f.shape[1]==BASE+OWN+EDGE*2 and len(f)==len(contexts)
            arrays.append(f);small.append(short);offset.append(offset[-1]+len(f))
    dest=dst/(p.stem+".npz")
    np.savez_compressed(dest,long=np.concatenate(arrays),short=np.concatenate(small),offset=offset)
    with gzip.open(dst/(p.stem+".jsonl.gz"),"wt",encoding="utf8") as f:
        for r in meta:dump(f,r)
    print(p.stem,len(meta),offset[-1],round(time.time()-start,2),flush=True)
def fit():
    packs=[]
    for p in panels():
        if "_train_" not in p.name:continue
        key=D/"cache"/p.stem
        meta=list(load_gz(key.with_suffix(".jsonl.gz")));v=np.load(key.with_suffix(".npz"))
        Y=[];W=[]
        for i,project,q,n,lens,gold in meta:
            Y.extend(j==gold for j in range(n));W.extend(1. if j==gold else 1/max(1,n-1) for j in range(n))
        packs.append((v["long"],v["short"],Y,W))
    y=np.concatenate([x[2] for x in packs]);weight=np.concatenate([x[3] for x in packs])
    models={};cost={}
    for name,(n,cols) in ARMS.items():
        X=np.concatenate([x[0 if n==120 else 1][:,cols] for x in packs]);start=time.time()
        clf=HistGradientBoostingClassifier(max_iter=75,max_leaf_nodes=15,min_samples_leaf=28,l2_regularization=1,learning_rate=.10,random_state=261118,early_stopping=False)
        models[name]=clf.fit(X,y,sample_weight=weight);cost[name]=round(time.time()-start,3)
    with (D/"models.pkl").open("wb") as f:pickle.dump(models,f)
    save("fit.json",{"train_pos":int(y.sum()),"train_pairs":len(y),"seconds":cost,"model_sha256":sha(D/"models.pkl")})
def predict():
    # Only deserialize our own local model, generated in the preceding fit phase.
    assert read("fit.json")["model_sha256"]==sha(D/"models.pkl")
    with (D/"models.pkl").open("rb") as f:models=pickle.load(f)
    outputs={}
    for p in panels():
        if "_test_" not in p.name:continue
        key=D/"cache"/p.stem;v=np.load(key.with_suffix(".npz"));meta=list(load_gz(key.with_suffix(".jsonl.gz")))
        full,short,offset=v["long"],v["short"],v["offset"]
        scores={a:m.predict_proba((full if ARMS[a][0]==120 else short)[:,ARMS[a][1]])[:,1] for a,m in models.items()}
        scores.update(jaccard3=full[:,0],jaccard120=full[:,1],bm25_3=full[:,2],bm25_120=full[:,3])
        dest=D/(p.stem+".pred.jsonl.gz")
        with gzip.open(dest,"wt",encoding="utf8") as f:
            for row,lo,hi in zip(meta,offset,offset[1:]):
                i,repo,hs,n,lens=row;ranks={a:np.argsort(-s[lo:hi],kind="stable").tolist() for a,s in scores.items()}
                dump(f,[i,repo,hs,lens,ranks])
        outputs[dest.name]=sha(dest)
    save("predictions_lock.json",{"utc":now(),"sha256":outputs,"model_sha256":sha(D/"models.pkl")})
def main():
    start=time.time();roster()
    with concurrent.futures.ProcessPoolExecutor(4) as ex:list(ex.map(extract,panels()))
    fit();predict()
    save("resource.json",{"cpu_wall_s":time.time()-start,"pid":os.getpid(),"feature_workers":4,"learner_threads":1})
if __name__=="__main__":main()
