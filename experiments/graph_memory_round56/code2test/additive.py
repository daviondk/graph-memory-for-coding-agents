"""Evaluate fixed additive and leave-one-project-out policies on the full base-commit test inventory."""
from collections import defaultdict
import hashlib
import json
import math
import os
import statistics

os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
import numpy as np
from source import HERE,R55,read,save,digest
from rank import features,is_test,name_score,past_groups
from grade import metrics,compare

def hash_(text):
    return hashlib.sha256(text.encode()).digest()

def rowsplit(name):
    roster=read(HERE/"roster.json");catalog=read(HERE/"catalog.json.gz")
    hist=read(HERE/"histories.json.gz");src=read(HERE/"publisher.json.gz");role=read(HERE/"role-author.json.gz")
    community=read(HERE/"community.json.gz")
    for q,r in sorted(roster.items()):
        if not r["eligible"]:continue
        cat=set(catalog[r["base"]]);paths=sorted(p for p in cat if is_test(p))
        assert len(paths)>=5
        ix={p:i for i,p in enumerate(paths)}
        anchors=set(r["anchors"])
        anchor_feat=[features(a) for a in anchors]
        name_values=[name_score(p,anchor_feat) for p in paths]
        names=sorted(paths,key=lambda p:(tuple(-v for v in name_values[ix[p]]),p))
        inputs=[[p for p in src[q][m] if p in ix] for m in ("embed4","embed8","pplx")]
        inputs.extend([role[q]["lexical"],role[q]["repomap"],[p for p in community[q]["codenib_dense"][:20] if p in ix],names])
        x=np.zeros((len(paths),10))
        for col,order in enumerate(inputs):
            for i,p in enumerate(order[:20],1):
                if p in ix:x[ix[p],col]=11/(10+i)
        x[:,7:]=np.array(name_values)
        stream=hist[r["base"]]["history"]
        selected=past_groups(stream,anchors,"local8")
        mem=np.zeros((len(ix),3));pop=np.zeros_like(mem)
        def add(counts,age,size,ps):
            for p in ps:
                if p not in ix or p in anchors:continue
                j=ix[p];counts[j,0]+=1;counts[j,1]+=1/(size-1)
                counts[j,2]=max(counts[j,2],1/(1+age/8))
        for age,sha,m,ps in selected:add(mem,age,m,ps)
        for age,(_,m,ps) in enumerate(stream):
            if ps:add(pop,age,m,ps)
        # Ties match the earlier local RRF: weight, newest witness, then file name.
        rid=sorted(np.flatnonzero(mem[:,0]),key=lambda j:(-mem[j,1],-mem[j,2],paths[j]))
        graph=np.zeros(len(ix))
        for i,j in enumerate(rid[:20],1):graph[j]=11/(10+i)
        for state in (mem,pop):state[:,:2]=np.log1p(state[:,:2])
        perm=sorted(range(len(ix)),key=lambda j:hash_(q+"\0"+paths[j]))
        mats={"static":x,"history":np.c_[x,mem],"popular":np.c_[x,pop],"shuffled":np.c_[x,mem[perm]]}
        # Base pretraining votes: Qwen4, Qwen8, tests-only Lexical and RepoMap, name.
        static=x[:,[0,1,3,4,6]].sum(1)
        fixed={m:[paths[i] for i in np.argsort(-scores,kind="stable")[:5]] for m,scores in {
            "base":static,"base_history":static+graph,"base_pplx":static+x[:,2],
            "base_pplx_history":static+x[:,2]+graph}.items()}
        yield q,dict(repo=r["repo"],base=r["base"],paths=paths,ix=ix,mats=mats,fixed=fixed)

def fit(train,model,labels):
    cases=[]
    for q,r in train:
        targets=[r["ix"][p] for p in labels[q] if p in r["ix"]]
        if targets:
            mat=r["mats"][model];cases.append((mat,mat[targets].mean(axis=0)))
    n=len(cases);dims=cases[0][0].shape[1];eye=np.eye(dims);weight=np.zeros(dims)
    def calc(w,hessian):
        loss=0.;grad=np.zeros(dims);hess=np.zeros((dims,dims))
        for mat,target in cases:
            scores=mat@w;hi=scores.max();exp=np.exp(scores-hi);mass=exp.sum()
            prob=exp/mass;mu=prob@mat
            loss+=math.log(mass)+hi-target@w;grad+=mu-target
            if hessian:hess+=(mat.T*prob)@mat-np.outer(mu,mu)
        return loss/n+.005*(w@w),grad/n+.01*w,hess/n+.01*eye
    for _ in range(60):
        obj,grad,hess=calc(weight,True)
        if max(abs(grad))<1e-8:break
        dx=np.linalg.solve(hess,grad);step=1.
        while calc(weight-step*dx,False)[0]>obj-1e-4*step*(grad@dx) and step>1e-12:
            step/=2
        weight-=step*dx
    obj,grad,_=calc(weight,False)
    assert max(abs(grad))<1e-7
    return weight,{"n_train":n,"loss":float(obj),"max_abs_gradient":float(max(abs(grad))),"w":weight.tolist()}

def main():
    cases=dict(rowsplit("code2test"))
    labels=read(HERE/"ground-truth.json.gz")
    repos=sorted({r["repo"] for r in cases.values()})
    outputs={q:dict(r["fixed"]) for q,r in cases.items()};fits={}
    for project in repos:
        train=[(q,r) for q,r in cases.items() if r["repo"]!=project]
        test=[(q,r) for q,r in cases.items() if r["repo"]==project]
        assert {q for q,_ in train}.isdisjoint(q for q,_ in test)
        fits[project]={}
        for model in ("static","history","shuffled","popular"):
            w,receipt=fit(train,model,labels);fits[project][model]=receipt
            for q,r in test:
                score=r["mats"][model]@w
                outputs[q][model]=[r["paths"][j] for j in np.argsort(-score,kind="stable")[:5]]
    save(HERE/"additive-ranks.json.gz",outputs)
    save(HERE/"additive-fits.json",fits)
    results={}
    for q,pred in outputs.items():
        scores={}
        for m,ranking in pred.items():
            v=metrics(ranking,labels[q])
            scores[m]=v+[int(set(labels[q])<=set(ranking))]
        results[q]={"repo":cases[q]["repo"],"base":cases[q]["base"],"metrics":scores}
    rows=list(results.values())
    pairs=[("base_pplx_history","base_pplx"),("base_history","base"),("base_pplx","base"),
           ("history","static"),("history","popular"),("history","shuffled"),("history","base_pplx_history")]
    prior=set(read(R55/"history.json.gz"))
    previous_repos={r["repo"] for r in read(R55/"history.json.gz").values()}
    result={"n":len(rows),"means":{m:list(map(statistics.fmean,zip(*(r["metrics"][m] for r in rows)))) for m in rows[0]["metrics"]},
            "comparisons":{a+"__"+b:compare(rows,a,b) for a,b in pairs}}
    for lab,subset in [("disjoint_base",[r for r in rows if r["base"] not in prior]),("disjoint_repo",[r for r in rows if r["repo"] not in previous_repos])]:
        result[lab]={a+"__"+b:compare(subset,a,b) for a,b in pairs}
    save(HERE/"additive-results.json",result)
    save(HERE/"additive-graded.json.gz",results)
    print({k:list(map(lambda x:round(x,4),v)) for k,v in result["means"].items()})
    print(result["comparisons"]["base_pplx_history__base_pplx"],result["comparisons"]["history__static"])
if __name__=="__main__":main()
