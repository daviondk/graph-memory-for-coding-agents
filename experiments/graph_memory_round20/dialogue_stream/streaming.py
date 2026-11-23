"""Use causal turn features and simulate irreversible online eviction under a token cap."""
import bisect
from collections import Counter
import gzip
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import sys
for v in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):os.environ[v]="1"
import numpy as np
from scipy.sparse import csr_matrix,hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from tokenizers import Tokenizer
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"dialogue_calibration"))
import run as prior
tr=prior.tr
def save(name,value):
    b=json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()+b"\n"
    (D/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith(".gz") else b)
def load(name):
    b=(D/name).read_bytes();return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)
def datasets(selected):
    cache={};data={};tok=Tokenizer.from_file("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
    for row in json.loads(tr.TARGET.read_bytes()):
        q=tr.digest(row["question_id"])
        if q not in selected:continue
        words=[];hashes=[];cost=[];xx=[];yy=[];groups=[];count=np.zeros((2,32),np.uint32);length=0
        for session in row["haystack_sessions"]:
            for t in session:
                text=t["content"];role=int(t["role"]=="user")
                if text not in cache:
                    f=tr.ds._traj_features(text,0,1,{})
                    c=len(tok.encode(text,add_special_tokens=False).ids);key=tr.digest(tr.norm(text))
                    cache[text]=(key,c,[f[k] for k in tr.BASE_KEYS[2:]],len(text.split()))
                h,c,shape,n=cache[text];bucket=min(31,math.floor(4*math.log2(1+n)))
                hist=count[role];percent=(hist[:bucket].sum()+.5*bucket+.5*(hist[bucket]+.5))/(hist.sum()+16)
                xx.append([math.log1p(length),1/(length+1),*shape]);groups.append([role,percent,role*percent])
                hist[bucket]+=1;length+=1;yy.append(int(t.get("has_answer") is True))
                words.append(text);hashes.append(h);cost.append(c)
        data[q]=(np.asarray(words,object),np.asarray(hashes),np.array(xx),np.array(groups),np.array(cost),np.array(yy))
    assert set(data)==selected;return data
def fit(train,te,data):
    union=lambda which,idx:np.concatenate([data[q][idx] for q in which])
    train_h=union(train,1);test_h=union(te,1)
    keep=~np.isin(train_h,np.unique(test_h));assert not set(train_h[keep])&set(test_h)
    y=union(train,5)[keep];assert len(set(y))==2
    t0=union(train,0)[keep];t1=union(te,0);vec=TfidfVectorizer(stop_words="english",min_df=1,max_features=10000)
    bag0=vec.fit_transform(t0);bag1=vec.transform(t1);pred={};models={}
    for arm in ("base","cal","small"):
        cols={k:union(k0,idx)[f] for k,k0,idx,f in (("b0",train,2,keep),("b1",te,2,slice(None)),("s0",train,3,keep),("s1",te,3,slice(None)))}
        if arm=="cal":num0=np.column_stack((cols["b0"],cols["s0"]));num1=np.column_stack((cols["b1"],cols["s1"]))
        else:
            name="b" if arm=="base" else "s";num0,num1=cols[name+"0"],cols[name+"1"]
        sc=StandardScaler().fit(num0);a,b=csr_matrix(sc.transform(num0)),csr_matrix(sc.transform(num1))
        if arm!="small":a,b=hstack([bag0,a]).tocsr(),hstack([bag1,b]).tocsr()
        lr=LogisticRegression(max_iter=1000,class_weight="balanced",random_state=0).fit(a,y);assert lr.n_iter_[0]<1000
        pred[arm]=lr.predict_proba(b)[:,1];models[arm]={"coefficients":len(lr.coef_[0]),"iters":int(lr.n_iter_[0]),"sha":hashlib.sha256(lr.coef_.tobytes()+lr.intercept_.tobytes()).hexdigest()}
    return pred,models,int(sum(~keep))
def simulate(scores,cost,cap):
    h=[];used=0;peak=0;rows=0
    for i,(s,c) in enumerate(zip(scores,cost,strict=True)):
        if c>cap:continue
        heapq.heappush(h,(float(s),-i,i,int(c)));used+=int(c)
        while used>cap:
            used-=heapq.heappop(h)[3]
        assert used<=cap
        peak=max(peak,used);rows=max(rows,len(h))
    return [sorted(z[2] for z in h),used,peak,rows]
def forecast():
    folds=prior.units()[:5];ids={q for te,_,_ in folds for q in te};data=datasets(ids);records={}
    for i,(te,train,_) in enumerate(folds):
        pred,model,removed=fit(train,te,data);results={};offset=0
        for q in te:
            words,hs,x,small,cost,y=data[q];n=len(cost);ar={a:p[offset:offset+n] for a,p in pred.items()};offset+=n
            ar.update({"cal/cost":ar["cal"]/np.maximum(cost,1),"small/cost":ar["small"]/np.maximum(cost,1),"fifo":np.arange(n),
                "shortest":-cost,"user_shortest":small[:,0]*1000000-cost})
            results[q]={str(cap):{k:simulate(s,cost,cap) for k,s in ar.items()} for cap in (2048,4096,8192)}
        save(f"pred-{i}.json.gz",results);records[str(i)]={"models":model,"removed":removed,"ids":te,"forecast":tr.sha(D/f"pred-{i}.json.gz")}
    assert len(ids)==62;save("forecast-seal.json",{"protocol":tr.sha(D/"PROTOCOL_RU.md"),"code":tr.sha(D/"streaming.py"),"dataset":tr.sha(tr.TARGET),"folds":records})
def score():
    lock=load("forecast-seal.json");assert lock["code"]==tr.sha(D/"streaming.py") and lock["dataset"]==tr.TARGET_SHA
    ys={tr.digest(row["question_id"]):[t.get("has_answer") is True for s in row["haystack_sessions"] for t in s] for row in json.loads(tr.TARGET.read_bytes())}
    out={}
    for i,v in lock["folds"].items():
        n=f"pred-{i}.json.gz";assert tr.sha(D/n)==v["forecast"]
        for q,cs in load(n).items():
            y=ys[q];total=sum(y);out[q]={}
            for cap,by in cs.items():
                for a,(kept,cost,peak,rows) in by.items():
                    hit=sum(y[j] for j in kept);assert len(set(kept))==len(kept) and cost<=peak<=int(cap)
                    out[q][cap+"/"+a]={"recall":hit/total if total else None,"full":int(hit==total) if total else None,"paid":cost,"slots":len(kept),"peak_slots":rows}
    ids=sorted(q for q,r in out.items() if r["4096/base"]["recall"] is not None);assert len(out)==62 and len(ids)==59
    sums={}
    for a in out[ids[0]]:
        sums[a]=dict(R=np.mean([out[q][a]["recall"] for q in ids]),FS=np.mean([out[q][a]["full"] for q in ids]),mean_paid=np.mean([r[a]["paid"] for r in out.values()]),mean_slots=np.mean([r[a]["slots"] for r in out.values()]))
    rng=np.random.default_rng(13);ix=rng.integers(0,len(ids),size=(10000,len(ids)));pairs={}
    for cap in ("2048","4096","8192"):
        for a,b in (("cal","base"),("cal","user_shortest"),("small","cal"),("cal/cost","cal"),("small/cost","user_shortest")):
            x=np.array([out[q][cap+"/"+a]["recall"]-out[q][cap+"/"+b]["recall"] for q in ids])
            pairs[cap+"/"+a+"-"+b]={"delta":float(x.mean()),"ci":np.quantile(x[ix].mean(axis=1),[.025,.975]).tolist(),"wins":int(sum(x>0)),"losses":int(sum(x<0))}
    save("outcomes.json.gz",out);save("results.json",{"n":62,"labelled":59,"arms":sums,"pairs":pairs});print(sums["4096/cal"],pairs["4096/cal-base"])
if __name__=="__main__":
    {"forecast":forecast,"score":score}[sys.argv[1]]()
