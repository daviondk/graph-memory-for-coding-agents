"""Full history turn-retention cross-fitting on the sealed source-disjoint LongMemEval panel."""
import os
for v in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[v]="1"
import collections
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np
import sklearn
from scipy.sparse import csr_matrix,hstack
from scipy.stats import rankdata
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

HERE=Path(__file__).resolve().parent
SIB=Path(os.environ.get("DIALOGUE_TRANSFER",str(HERE.parent/"dialogue_transfer")))
sys.path.insert(0,str(SIB))
import study as tr
ARM=("original","role_pct","calibrated","edge","shifted")
PROTO="398935734a31ae98c802b393a3c42c229f2867733385e2dcfb5a6db7b511d1c2"

def save(n,obj):
    p=HERE/n
    data=json.dumps(obj,ensure_ascii=True,separators=(",",":"),allow_nan=False).encode()+b"\n"
    if n.endswith(".gz"):
        data=gzip.compress(data,compresslevel=4,mtime=0)
    if p.exists():
        assert data==p.read_bytes(),n
    else:
        tmp=p.with_suffix(p.suffix+".tmp"+str(os.getpid()))
        tmp.write_bytes(data)
        tmp.replace(p)

def load(n,base=HERE):
    b=(base/n).read_bytes()
    return json.loads(gzip.decompress(b) if n.endswith("gz") else b)

def units():
    s=load("split.json.gz",SIB)
    ids=load("observed-session-ids.json.gz",SIB)
    res={q:{"c"+x for x in hs}|{"i"+x for x in ids[q]} for q,hs in s["histories"].items()}
    strict=sorted(s["selected"])
    other=sorted(set(res)-set(strict))
    folds=[]
    for i in range(5):
        te=strict[i::5]
        folds.append((te,sorted(set(strict)-set(te)),"strict"))
    for i in range(0,len(other),16):
        te=other[i:i+16]
        test_ids=set.union(*(res[q] for q in te))
        folds.append((te,[q for q in strict if not (res[q] & test_ids)],"additional"))
    for te,train,_ in folds:
        assert not set.union(*(res[q] for q in te)).intersection(set.union(*(res[q] for q in train)))
    assert len({q for te,_,_ in folds for q in te})==500
    return folds

def make_data():
    dat={}
    text_cache={}
    edge_cache={}
    text_id={}
    for q in json.loads(tr.TARGET.read_bytes()):
        qh=tr.digest(q["question_id"])
        texts=[]
        tid=[]
        raw=[]
        e=[]
        roles=[]
        gold=[]
        for ss in q["haystack_sessions"]:
            pair=tuple((t["role"],t["content"]) for t in ss)
            if not pair:
                continue
            if pair not in edge_cache:
                edge_cache[pair]=tr.edge_arrays(pair)
            e.append(edge_cache[pair])
            for t in ss:
                x=t["content"]
                if x not in text_cache:
                    f=tr.ds._traj_features(x,0,1,{})
                    nid=tr.digest(tr.norm(x))
                    text_cache[x]=(nid,[f[k] for k in tr.BASE_KEYS[2:]],len(x.split()))
                nid,f,l=text_cache[x]
                texts.append(x)
                tid.append(text_id.setdefault(nid,len(text_id)))
                raw.append(f+[l])
                roles.append(t["role"]=="user")
                gold.append(t.get("has_answer") is True)
        n=len(texts)
        st=np.array(raw,dtype=float)
        idx=np.arange(n)
        b=np.column_stack((idx/n,1/(n-idx),st[:,:-1]))
        role=np.array(roles)
        pct=np.zeros(n,dtype=float)
        for v in (True,False):
            m=role==v
            if any(m):
                pct[m]=(rankdata(st[m,-1],method="average")-.5)/sum(m)
        c=np.column_stack((role,pct,role*pct))
        dat[qh]=(np.array(texts,dtype=object), np.array(tid), b,c,np.concatenate(e),np.array(gold,dtype=np.int8))
    return dat

def train_fold(i,fold,dat):
    te,train,section=fold
    test_hashes=np.unique(np.concatenate([dat[q][1] for q in te]))
    train_hashes=np.concatenate([dat[q][1] for q in train])
    keep=~np.isin(train_hashes,test_hashes)
    raw_gold=np.concatenate([dat[q][-1] for q in train])
    rm_pos=int(sum(raw_gold[~keep].astype(np.int64)))
    rm_neg=int((~keep).sum())-rm_pos
    assert np.intersect1d(train_hashes[keep],test_hashes).size==0
    y=raw_gold[keep]
    train_text=np.concatenate([dat[q][0] for q in train])[keep]
    x0=np.concatenate([dat[q][2] for q in train])[keep]
    c0=np.concatenate([dat[q][3] for q in train])[keep]
    e0=np.concatenate([dat[q][4] for q in train])[keep]
    test_text=np.concatenate([dat[q][0] for q in te])
    x1=np.concatenate([dat[q][2] for q in te])
    c1=np.concatenate([dat[q][3] for q in te])
    e1=np.concatenate([dat[q][4] for q in te])
    pred={}
    degenerate=len(np.unique(y))<2
    if not degenerate:
        vec=TfidfVectorizer(stop_words="english",min_df=1,max_features=10000)
        t0=vec.fit_transform(train_text)
        t1=vec.transform(test_text)
    for a in ARM:
        def extra(x,c,e):
            if a=="original":
                return x
            if a=="role_pct":
                return c
            if a=="calibrated":
                return np.column_stack((x,c))
            return np.column_stack((x,c,e[:,0 if a=="edge" else 1]))
        if degenerate:
            pred[a]=np.full(len(test_text),np.mean(y) if len(y) else .5)
            continue
        v=extra(x0,c0,e0)
        sc=StandardScaler().fit(v)
        m0=csr_matrix(sc.transform(v))
        m1=csr_matrix(sc.transform(extra(x1,c1,e1)))
        if a!="role_pct":
            m0=hstack([t0,m0]).tocsr()
            m1=hstack([t1,m1]).tocsr()
        clf=LogisticRegression(max_iter=1000,class_weight="balanced",random_state=0)
        clf.fit(m0,y)
        assert max(clf.n_iter_)<1000
        pred[a]=clf.predict_proba(m1)[:,1]
    rows=[]
    cursor=0
    for q in te:
        n=len(dat[q][0])
        rows.append(dict(id=q,score={a:s[cursor:cursor+n].tolist() for a,s in pred.items()},
                         user=dat[q][3][:,0].astype(int).tolist()))
        cursor+=n
    file=f"pred-{i:02d}.json.gz"
    save(file,rows)
    audit=dict(fold=i,section=section,train=train,test=te,train_remaining=len(y),train_pos=int(y.astype(np.int64).sum()),
       n_train_before=len(raw_gold),removed_train_pos=rm_pos,removed_train_neg=rm_neg,
       remaining_normalized_train_test_intersection=0,train_test_session_intersection=0,degenerate=degenerate,
       prediction_hash=tr.sha(HERE/file))
    save(f"fold-{i:02d}.json",audit)
    print(f"{section} fold {i}: {len(train)} train histories; {len(y)} surviving turns; {len(te)} test histories",flush=True)

def main():
    assert tr.sha(HERE/"PROTOCOL_RU.md")==PROTO and tr.sha(tr.TARGET)==tr.TARGET_SHA
    assert tr.sha(SIB/"split.json.gz")=="070b36e96ed74466041b18a019af32de0d21fbe9e63176e634cc11cde81e1423"
    f=units()
    save("split.json",dict(folds=[dict(train=t,test=e,section=k) for e,t,k in f],protocol=PROTO,
         prior_split=tr.sha(SIB/"split.json.gz"), prior_source_ids=tr.sha(SIB/"observed-session-ids.json.gz"),
         code=tr.sha(Path(__file__)), prior_edges=tr.sha(tr.PREV),lre=tr.REV,source=tr.TARGET_SHA,
         sklearn=sklearn.__version__,numpy=np.__version__))
    dat=make_data()
    job=sys.argv[1] if len(sys.argv)>1 else "all"
    mod,par=map(int,job.split("/")) if job!="all" else (0,1)
    for i,fold in enumerate(f):
        if i%par!=mod:
            continue
        audit=HERE/f"fold-{i:02d}.json"
        if audit.exists():
            assert load(audit.name)["prediction_hash"]==tr.sha(HERE/f"pred-{i:02d}.json.gz")
            continue
        train_fold(i,fold,dat)
    # Persist evaluation truth separately, only after this worker's forecasts are frozen.
    save(f"gold-{mod}-of-{par}.json.gz",{q:dat[q][-1].tolist() for i,(te,_,_) in enumerate(f) if i%par==mod for q in te})
if __name__=="__main__":
    main()
