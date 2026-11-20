"""Unseen later repository test with two pre-trained conditional experts and a gate from past evidence."""
from run import *
from sklearn.ensemble import HistGradientBoostingClassifier as HGB
from features import compute
import math
def short_key(p):return "first" if "first" in p.stem else "random"
def classifier(small=False):
    return HGB(max_iter=50 if small else 75,max_leaf_nodes=7 if small else 15,min_samples_leaf=28,l2_regularization=1,learning_rate=.1,random_state=261118,early_stopping=False)
def summary(x):
    vals=[np.log1p(len(x))]
    for j in (0,1,2,3,19,21,26,28,29,30,31,32,34,35,36,37):
        col=x[:,j];s=np.sort(col)
        vals.extend((float(col.max()),float(col.mean()),float(s[-1]-s[-2] if len(s)>1 else s[0]),float(np.mean(col>0))))
    return vals
def select():
    used=set();hashes=set()
    for p in panels():
        cache=D/"cache"/(p.stem+".jsonl.gz")
        for r in load_gz(cache):used.add(r[1].casefold());hashes.add(r[2])
    candidates=collections.defaultdict(list);stats=collections.Counter()
    for p in sorted((D/"transfer_inputs").glob("*.parquet")):
        i=-1;s=short_key(p)
        for batch in pq.ParquetFile(p).iter_batches(batch_size=40,columns=["repo_name","context","cropped_code"]):
            for o in batch.to_pylist():
                i+=1;stats[s+"_initial"]+=1;r=o['repo_name'].casefold()
                if r in used:stats[s+"_oldrepo"]+=1;continue
                text=o["cropped_code"];qh=hashlib.sha256(text.encode()).hexdigest()
                if qh in hashes:stats[s+"_oldcode"]+=1;continue
                if len(o["context"])<5:stats[s+"_shortslate"]+=1;continue
                tie=hashlib.sha256(f"r3time|{p.name}|{i}".encode()).hexdigest()
                candidates[s].append((tie,p.name,i,r,qh,len(text.splitlines())))
    out=[];sel={}
    for s,cs in candidates.items():
        seen=set()
        for _,f,i,r,h,num in sorted(cs):
            if (r,h) in seen:continue
            seen.add((r,h));out.append([s,f,i,r,h,num])
            if len(seen)==1500:break
        sel[s]=len(seen)
    save("transfer_roster.json",out);save("transfer_selection.json",dict(flow=stats,selected=sel))
def train():
    mats={"first":[],"random":[]};ys={s:[] for s in mats};ws={s:[] for s in mats};gx=[];gy=[];malformed=[]
    fullcols=ARMS["transition"][1]
    for p in panels():
        if "_train_" not in p.name:continue
        s="first" if "_cff_" in p.name else "random"
        key=D/"cache"/p.stem;v=np.load(key.with_suffix(".npz"));F=v["long"];offset=v["offset"]
        for row,lo,hi in zip(load_gz(key.with_suffix(".jsonl.gz")),offset,offset[1:]):
            i,r,q,n,lens,g=row
            if g<0 or g>=n:malformed.append([p.stem,i,g,n]);continue
            x=F[lo:hi];mats[s].append(x[:,fullcols]);ys[s].extend(int(j==g) for j in range(n))
            ws[s].extend(1. if j==g else 1/(n-1) for j in range(n));gx.append(summary(x));gy.append(s=="random")
    experts={s:classifier().fit(np.concatenate(X),np.array(ys[s]),sample_weight=np.array(ws[s])) for s,X in mats.items()}
    gate=classifier(small=True).fit(np.array(gx),np.array(gy))
    with (D/"experts.pkl").open("wb") as f:pickle.dump((experts,gate),f)
    clean={}
    for a in ("owner","transition"):
        C=ARMS[a][1];clean[a]=classifier().fit(np.concatenate([np.concatenate(mats[s])[:,C] for s in mats]),np.concatenate([ys[s] for s in mats]),sample_weight=np.concatenate([ws[s] for s in mats]))
    with (D/"clean.pkl").open("wb") as f:pickle.dump(clean,f)
    save("transfer_fit.json",{"invalid_train":malformed,"valid_train":len(gy),"sha256":{f:sha(D/f) for f in ["experts.pkl","clean.pkl","models.pkl"]}})
def clean_predict():
    with (D/"clean.pkl").open("rb") as f:M=pickle.load(f)
    with gzip.open(D/"clean_predictions.jsonl.gz","wt",encoding="utf8") as out:
        for p in panels():
            if "_test_" not in p.name:continue
            v=np.load(D/"cache"/(p.stem+".npz"));F=v["long"];offset=v["offset"]
            pred={a:m.predict_proba(F[:,ARMS[a][1]])[:,1] for a,m in M.items()}
            for i,(lo,hi) in enumerate(zip(offset,offset[1:])):dump(out,[p.stem,i,{a:np.argsort(-pr[lo:hi],kind="stable").tolist() for a,pr in pred.items()}])
def predict():
    ids=collections.defaultdict(dict)
    for s,f,i,r,h,nlines in read("transfer_roster.json"):ids[f][i]=(r,h,nlines)
    with (D/"experts.pkl").open("rb") as f:exp,gate=pickle.load(f)
    with (D/"models.pkl").open("rb") as f:orig=pickle.load(f)
    rows=[];features=[];cuts=[0];gx=[]
    for p in sorted((D/"transfer_inputs").glob("*.parquet")):
        i=-1
        for batch in pq.ParquetFile(p).iter_batches(batch_size=40,columns=["cropped_code","context"]):
            for o in batch.to_pylist():
                i+=1
                if i not in ids[p.name]:continue
                code=o["cropped_code"];cs=[z["snippet"] for z in o["context"]];r,h,ln=ids[p.name][i]
                assert hashlib.sha256(code.encode()).hexdigest()==h
                f=compute(code,cs,120);features.append(f);gx.append(summary(f));cuts.append(cuts[-1]+len(f));rows.append((p.name,i,r,h,ln,[len(c) for c in cs]))
    F=np.concatenate(features);g=gate.predict_proba(np.array(gx))[:,1]
    score={a:m.predict_proba(F[:,ARMS[a][1]])[:,1] for a,m in orig.items() if a in ("flat","owner","transition","placebo")}
    for a,m in exp.items():score[a]=m.predict_proba(F[:,ARMS["transition"][1]])[:,1]
    with gzip.open(D/"transfer_predictions.jsonl.gz","wt",encoding="utf8") as f:
        for meta,lo,hi,q in zip(rows,cuts,cuts[1:],g):
            v={a:pr[lo:hi] for a,pr in score.items()}
            def posterior(p):
                odds=p/np.clip(1-p,1e-8,1);return odds/odds.sum()
            prior,repeat=posterior(v["first"]),posterior(v["random"])
            v["mix"]=.5*prior+.5*repeat;v["gate"]=(1-q)*prior+q*repeat
            ranks={a:np.argsort(-z,kind="stable").tolist() for a,z in v.items()}
            dump(f,[*meta,float(q),ranks])
def main():
    select();train()
    pins=["transfer.py","TRANSFER_PROTOCOL.md","transfer_sources.json","transfer_roster.json","transfer_fit.json","experts.pkl","clean.pkl"]
    save("transfer_method_lock.json",{"utc":now(),"sha":{f:sha(D/f) for f in pins}})
    clean_predict();predict()
    save("transfer_predictions_lock.json",{"utc":now(),"sha":{f:sha(D/f) for f in ["transfer_predictions.jsonl.gz","clean_predictions.jsonl.gz","transfer_method_lock.json"]}})
if __name__=="__main__":main()
