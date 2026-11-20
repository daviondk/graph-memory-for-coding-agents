"""Fix roster, extract without test labels, fit equal classifiers, then seal all predictions."""
import os
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):
    os.environ[key]="1"
import gzip
import json
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
from functools import lru_cache
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from data_io import D,R3,files,hashstr,read,rows,sha,write
from memory import encode,features,FLAT,LOCAL,OWNER
import sys
sys.path.insert(0,str(R3/"lib"))
from tokenizers import Tokenizer
TOK=Tokenizer.from_file(str(R3/"inputs/codegen_tokenizer.json"))
@lru_cache(2048)
def nt(s):return len(TOK.encode(s,add_special_tokens=False).ids)

def shard(p):
    start=time.monotonic();train="_train_" in p.name
    select=dict(read("roster.json")[p.stem])
    cols=["code","context","repo_name"]+ (["gold_snippet_index"] if train else [])
    meta=[];x={3:[],10:[]};offset=[0];cache=D/"cache";cache.mkdir(exist_ok=True)
    for i,row in enumerate(rows(p,cols)):
        if i not in select:continue
        ctx=row["context"];memo=encode(ctx);code=row["code"]
        n=len(ctx);idx=select[i]
        if train and not 0<=row["gold_snippet_index"]<n:continue
        infos=[idx,row["repo_name"],len(ctx),[nt(t) for t in ctx],hashstr(code)]
        if train:infos.append(row["gold_snippet_index"])
        meta.append(infos)
        shift=1+int(hashstr(f"shift|{code.splitlines()[-3:]}")[:10],16)%max(1,n-1)
        for keep in (3,10):
            f=features(code,memo,keep)
            f=np.column_stack([f,np.roll(f[:,OWNER:],shift,axis=0)])
            x[keep].append(f)
        offset.append(offset[-1]+n)
    np.savez_compressed(cache/(p.stem+".npz"),offset=np.array(offset),f3=np.row_stack(x[3]),f10=np.row_stack(x[10]))
    (cache/(p.stem+".json")).write_text(json.dumps(meta),encoding="utf8")
    print(p.name,len(meta),round(time.monotonic()-start,2),flush=True)

ARMS={"flat":list(range(FLAT)),"local":list(range(LOCAL)),"owner":list(range(OWNER)),"graph":list(range(43)),"permute":[*range(OWNER),*range(43,51)]}
def read_cache(p):
    stem=D/"cache"/p.stem
    return np.load(stem.with_suffix(".npz")),json.loads(stem.with_suffix(".json").read_bytes())
def train():
    blocks=[read_cache(p) for p in files("java","train")]
    y=[];sw=[]
    for _,meta in blocks:
        for _,proj,n,sizes,h,g in meta:
            y.extend([i==g for i in range(n)]);sw.extend([1 if i==g else 1/max(n-1,1) for i in range(n)])
    out={}
    for keep in (3,10):
        X=np.row_stack([a[f"f{keep}"] for a,meta in blocks])
        for name,cols in ARMS.items():
            m=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,min_samples_leaf=28,learning_rate=.10,l2_regularization=1,random_state=261119,early_stopping=False)
            out[keep,name]=m.fit(X[:,cols],y,sample_weight=sw)
    with (D/"models.pkl").open("wb") as f:pickle.dump(out,f)
    write("fit.json",{"retained_train_samples":int(sum(y)),"pairs":len(y),"sha256":sha(D/"models.pkl")})
    return out
def predict(models):
    outputs={}
    for lang in ("java","python"):
        with gzip.open(D/(lang+".pred.jsonl.gz"),"wt",encoding="utf8") as out:
            for p in files(lang,"test"):
                data,meta=read_cache(p)
                for keep in (3,10):
                    x=data[f"f{keep}"];vs={a:m.predict_proba(x[:,ARMS[a]])[:,1] for (k,a),m in models.items() if k==keep}
                    for rec,lo,hi in zip(meta,data["offset"],data["offset"][1:]):
                        i,repo,n,sz,h=rec
                        ranks={a:np.argsort(-s[lo:hi],kind="stable").tolist() for a,s in vs.items()}
                        cnt=(x[lo:hi,OWNER]>0).sum()
                        out.write(json.dumps([p.stem.rsplit("_",1)[0],i,keep,repo,sz,h,int(cnt),ranks],separators=(",",":"))+"\n")
        outputs[lang+".pred.jsonl.gz"]=sha(D/(lang+".pred.jsonl.gz"))
    write("prediction_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"model":sha(D/"models.pkl"),"files":outputs})
def main():
    start=time.monotonic()
    paths=["PROTOCOL_RU.md","data_io.py","memory.py","experiment.py","sources.json","roster.json","native_roster.json","native_run.py","publisher_repobench.py","publisher_arms.py","publisher_common.py"]
    write("method_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"files":{n:sha(D/n) for n in paths},
        "python_data":{p.name:sha(p) for p in files("python","test")},"tokenizer_sha256":sha(R3/"inputs/codegen_tokenizer.json")})
    panels=[*files("java","train"),*files("java","test"),*files("python","test")]
    with ProcessPoolExecutor(4) as pool:list(pool.map(shard,panels))
    models=train();predict(models)
    write("run.json",{"seconds":time.monotonic()-start,"workers":4,"threads_fit":1})
if __name__=="__main__":main()
