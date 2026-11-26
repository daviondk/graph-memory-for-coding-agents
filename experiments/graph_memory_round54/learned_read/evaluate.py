"""Fit strictly out-of-repository, query-weighted pointwise models; score only sealed OOF decisions."""
import os
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from collections import Counter
from features import D,SRC,read,put,sha

MODELS=("static7","static8","memory8")
def design(data,ids):
    paths=[];groups=[];weights=[];ranks=[];slices={}
    for q in ids:
        r=data[q];start=len(paths);n=len(r["paths"])
        paths.extend(r["paths"]);groups.extend([r["group"]]*n);weights.extend([1/n]*n);ranks.extend(r["ranks"])
        slices[q]=slice(start,start+n)
    a=np.array(ranks,dtype=float)
    vals=np.zeros_like(a)
    positive=a>0
    vals[positive]=1/np.log2(1+a[positive])
    base=np.c_[np.ones(len(a)),vals[:,:7],np.zeros(len(a))]
    matrices={k:base.copy() for k in MODELS}
    matrices["memory8"][:,-1]=vals[:,-1]
    matrices["static8"][:,-1]=positive[:,:7].mean(axis=1)
    return matrices,np.array(weights),np.array(groups),slices
def sigmoid(x):return np.exp(-np.logaddexp(0,-x))
def fit(X,y,mass):
    """Newton steps minimize summed query-balanced log loss + half the squared norm."""
    beta=np.zeros(X.shape[1]);penalty=np.eye(len(beta));penalty[0,0]=0
    def obj(b):
        logits=X@b
        return float(mass@(np.logaddexp(0,logits)-y*logits)+.5*(b[1:]@b[1:]))
    for it in range(100):
        p=sigmoid(X@beta);g=X.T@(mass*(p-y))+penalty@beta
        if np.max(np.abs(g))<1e-8:break
        A=X.T@((mass*p*(1-p))[:,None]*X)+penalty
        step=np.linalg.solve(A,g);rate=1.;cur=obj(beta)
        while obj(beta-rate*step)>cur+1e-12:
            rate*=.5
            if rate<1e-9:raise ArithmeticError("line search did not descend")
        beta-=rate*step
    else:raise ArithmeticError("fit did not converge")
    return beta,dict(iterations=it,gradient=float(np.max(np.abs(g))),loss=obj(beta),weights=beta.tolist())
def run(data,labels,exclude):
    ids=[q for q in sorted(data) if data[q]["group"]!=exclude]
    matrices,weight,rows,sl=design(data,ids)
    groups=sorted(set(rows));dec={};probs={};folds={}
    for g in groups:
        train_ids=[q for q in ids if data[q]["group"]!=g]
        test_ids=[q for q in ids if data[q]["group"]==g]
        train=rows!=g
        assert not set(train_ids)&set(test_ids) and np.isclose(weight[train].sum(),len(train_ids))
        y=np.array([float(p in labels[q]) for q in train_ids for p in data[q]["paths"]])
        assert len(y)==train.sum()
        f=dict(train_ids=train_ids,test_ids=test_ids,train_groups=sorted(set(groups)-{g}),models={})
        for model in MODELS:
            mat=matrices[model];beta,details=fit(mat[train],y,weight[train]);f["models"][model]=details
            for q in test_ids:
                logits=mat[sl[q]]@beta
                selected=int(np.argmax(logits))
                a=data[q]["paths"]
                dec.setdefault(q,dict(rrf7=data[q]["rrf7"],rrf3=data[q]["rrf3"]))[model]=a[selected]
                probs.setdefault(q,{})[model]=sigmoid(logits).tolist()
        folds[g]=f
    assert set(dec)==set(ids)
    return dec,probs,folds
def metrics(data,labels,dec):
    ids=sorted(dec);g,idx=np.unique([data[q]["group"] for q in ids],return_inverse=True)
    den=np.bincount(idx);rng=np.random.default_rng(541907)
    draws=rng.integers(len(g),size=(10000,len(g)));counts={};out={}
    for m in [*MODELS,"rrf7","rrf3","strict"]:
        a=[]
        for q in ids:
            past=set(data[q]["strict"]);gold=labels[q]
            p=dec[q][m] if m!="strict" else None
            assert p not in past and gold
            hit=int(p in gold);rec=len(gold & (past|({p} if p else set())))/len(gold)
            a.append([hit,rec])
        counts[m]=np.array(a);out[m]=dict(new_hits=int(counts[m][:,0].sum()),new_hit_pct=100*counts[m][:,0].mean(),
             total_recall_pct=100*counts[m][:,1].mean())
    contrasts={};bygroup={}
    for left,right in [(x,y) for x,y in [("memory8","static7"),("memory8","static8"),("memory8","rrf7"),("memory8","rrf3"),("static7","rrf7")]]:
        d=counts[left]-counts[right];c={}
        for j,m in enumerate(("new_hit","total_recall")):
            summed=np.bincount(idx,weights=d[:,j]);boot=100*summed[draws].sum(1)/den[draws].sum(1)
            c[m]=dict(delta_pp=100*d[:,j].mean(),ci95_pp=list(np.quantile(boot,[.025,.975])),equal_repo_pp=100*(summed/den).mean(),
                wins=int((d[:,j]>1e-12).sum()),losses=int((d[:,j]< -1e-12).sum()))
        c["changed"]=sum(dec[q][left]!=dec[q][right] for q in ids)
        contrasts[left+" vs "+right]=c
    for repo in g:
        mask=idx==list(g).index(repo);bygroup[repo]=dict(n=int(mask.sum()),hits={m:int(z[mask,0].sum()) for m,z in counts.items()})
    return dict(n=len(ids),repos=len(g),summary=out,contrasts=contrasts,by_repo=bygroup)
def main():
    reg=read(D/"registration.json")
    assert reg["projection"]==sha(D/"projection.json.gz") and reg["protocol"]==sha(D/"PROTOCOL_RU.md") and reg["model"]==sha(D/"evaluate.py")
    data=read(D/"projection.json.gz");labels={q:set(ls) for q,ls in read(SRC/"labels.json.gz").items()}
    assert set(data)==set(labels)
    ng=Counter(r["group"] for r in data.values());largest=sorted(ng,key=lambda k:(-ng[k],k))[0]
    result={};decisions={};models={};scores={}
    for name,drop in [("all",None),("without_largest",largest)]:
        dec,probs,folds=run(data,labels,drop);decisions[name]=dec;models[name]=folds;scores[name]=probs
    put("oof-decisions.json.gz",decisions);put("oof-models.json.gz",models);put("oof-probabilities.json.gz",scores)
    put("prediction-seal.json",dict(projection=reg["projection"],registration=sha(D/"registration.json"),labels=sha(SRC/"labels.json.gz"),model=sha(D/"evaluate.py"),
            decisions=sha(D/"oof-decisions.json.gz"),parameters=sha(D/"oof-models.json.gz"),probabilities=sha(D/"oof-probabilities.json.gz")))
    for name,dec in decisions.items():result[name]=metrics(data,labels,dec)
    present=[q for q,r in data.items() if any(c[-1]>0 for c in r["ranks"])]
    work=decisions["all"]
    result["diagnostics"]=dict(largest=largest,positive_candidates=sum(len(set(row["paths"])&labels[q]) for q,row in data.items()),candidates=sum(len(r["paths"]) for r in data.values()),
        verified_proposal_queries=len(present),strict_already_complete=sum(labels[q]<=set(r["strict"]) for q,r in data.items()),
        eligible_pool_contains_unread_gold=sum(bool(set(r["paths"])&labels[q]) for q,r in data.items()),
        memory_weights=[v["models"]["memory8"]["weights"][-1] for v in models["all"].values()],
        movement_without_proposals=sum(work[q]["memory8"]!=work[q]["static7"] for q in set(data)-set(present)))
    put("results.json",result)
    print(json_text(result["all"]["summary"]));print(json_text(result["all"]["contrasts"]["memory8 vs static7"]))
def json_text(x):
    import json
    return json.dumps(x)
if __name__=="__main__":main()
