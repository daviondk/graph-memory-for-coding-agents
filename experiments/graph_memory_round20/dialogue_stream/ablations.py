"""Sealed component ablation and source-purged extension to all LongMemEval-S histories."""
from streaming import prior,tr,D,np,csr_matrix,hstack,TfidfVectorizer,StandardScaler,LogisticRegression,save,load,datasets,simulate
from collections import Counter
ARMS={"base":(),"role":(0,),"pct":(1,),"add":(0,1),"cal":(0,1,2)}
def forecast():
    splits=prior.units(); ids={q for te,_,_ in splits for q in te};assert len(ids)==500
    data=datasets(ids);hashes={}
    for i,(te,train,kind) in enumerate(splits):
        get=lambda keys,index:np.concatenate([data[q][index] for q in keys])
        doomed=np.unique(get(te,1));mask=~np.isin(get(train,1),doomed)
        assert not set(get(train,1)[mask])&set(doomed);y=get(train,5)[mask]
        v=TfidfVectorizer(stop_words="english",min_df=1,max_features=10000);bag0=v.fit_transform(get(train,0)[mask]);bag1=v.transform(get(te,0))
        b0,b1=get(train,2)[mask],get(te,2);c0,c1=get(train,3)[mask],get(te,3);allp={}
        for arm,idx in ARMS.items():
            x0=np.column_stack((b0,c0[:,idx]));x1=np.column_stack((b1,c1[:,idx]))
            sc=StandardScaler().fit(x0);x0=hstack([bag0,csr_matrix(sc.transform(x0))]).tocsr()
            x1=hstack([bag1,csr_matrix(sc.transform(x1))]).tocsr();lr=LogisticRegression(max_iter=1000,class_weight="balanced",random_state=0).fit(x0,y)
            assert lr.n_iter_[0]<1000
            allp[arm]=lr.predict_proba(x1)[:,1]
        out={};cursor=0
        ref=load(f"pred-{i}.json.gz") if kind=="strict" else None
        for q in te:
            cost=data[q][4];n=len(cost);piece=slice(cursor,cursor+n);cursor+=n
            out[q]={a:simulate(p[piece],cost,4096) for a,p in allp.items()}
            if ref is not None:
                for a in ("base","cal"):assert out[q][a]==ref[q]["4096"][a]
        path=f"component-{i}.json.gz";save(path,out)
        trainy=get(train,5);hashes[path]={"sha":tr.sha(D/path),"kind":kind,"dropped_pos":int(trainy[~mask].sum()),"dropped_neg":int((~mask).sum()-trainy[~mask].sum())}
    save("components-seal.json",{"code":tr.sha(D/"ablations.py"),"plan":tr.sha(D/"ABLATIONS_RU.md"),"base":tr.sha(D/"streaming.py"),"files":hashes})
def score():
    import json
    from statistics import mean
    lock=load("components-seal.json");assert all(tr.sha(D/f)==row["sha"] for f,row in lock["files"].items())
    truth={tr.digest(r["question_id"]):np.array([t.get("has_answer") is True for s in r["haystack_sessions"] for t in s]) for r in json.loads(tr.TARGET.read_bytes())}
    out={}
    for f,entry in lock["files"].items():
        for q,arms in load(f).items():
            y=truth[q];assert q not in out
            out[q]={"panel":entry["kind"],"n":len(y),"p":int(y.sum()),"arms":{a:{"hit":int(y[row[0]].sum()),"tokens":row[1],"slots":len(row[0])} for a,row in arms.items()}}
    result={}
    for kind in ("strict","additional","all"):
        ids=sorted(q for q,row in out.items() if (kind=="all" or row["panel"]==kind) and row["p"]>0)
        by={a:np.array([out[q]["arms"][a]["hit"]/out[q]["p"] for q in ids]) for a in ARMS}
        effects={}
        for a,b in (("cal","base"),("role","base"),("pct","base"),("add","role"),("cal","role"),("cal","add")):
            x=by[a]-by[b];z={"delta":float(x.mean()),"wins":int(sum(x>0)),"losses":int(sum(x<0))}
            if kind=="strict":
                ix=np.random.default_rng(13).integers(0,len(ids),size=(10000,len(ids)));z["ci"]=np.quantile(x[ix].mean(axis=1),[.025,.975]).tolist()
            effects[a+"-"+b]=z
        result[kind]={"n":len(ids),"recall":{a:float(x.mean()) for a,x in by.items()},"full":{a:float((x==1).mean()) for a,x in by.items()},"pairs":effects}
    assert len(out)==500 and result["all"]["n"]==479
    save("components-outcomes.json.gz",out);save("components-results.json",result);print({k:v["recall"] for k,v in result.items()})
if __name__=="__main__":
    import sys
    {"forecast":forecast,"score":score}[sys.argv[1]]()
