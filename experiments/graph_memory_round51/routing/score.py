"""Score four sealed policies with the official HotpotQA evaluator."""
from collections import Counter
import ast
from contextlib import redirect_stdout
from io import StringIO
import importlib.util
import json
import math
import sys

import numpy as np
from study import D,P,FILES,N,get,put,sha,columns,check,EVAL_HASH


def official():
    assert sha(P/"official.py")==EVAL_HASH
    sys.modules.setdefault("ujson",json)
    spec=importlib.util.spec_from_file_location("hotpot_eval",P/"official.py")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sign_p(delta):
    w=np.abs(delta[delta!=0])
    k=len(w)
    obs=abs(math.fsum(delta))
    extreme=0
    if k<=20:
        draws=1<<k
        for offset in range(0,draws,2048):
            rows=np.arange(offset,min(draws,offset+2048),dtype=np.int64)
            signs=2*((rows[:,None]>>np.arange(k))&1)-1
            extreme+=int((np.abs(signs@w)>=obs-1.e-12).sum())
        p=extreme/draws
    else:
        draws=1000000
        rng=np.random.default_rng(500731)
        for offset in range(0,draws,2000):
            signs=2*rng.integers(0,2,size=(min(2000,draws-offset),k),dtype=np.int8)-1
            extreme+=int((np.abs(signs@w)>=obs-1.e-12).sum())
        p=(extreme+1)/(draws+1)
    return dict(p=p,nonzero=k,extreme=extreme,draws=draws,seed=500731,exact=bool(k<=20))


def analyze(rows):
    keys=sorted(rows)
    names=["router","linked_dense","dense","adaptive"]
    vals=np.array([[rows[q]["arms"][a] for a in names] for q in keys])
    contrasts={}
    pairs=[("router","linked_dense"),("router","dense"),("router","adaptive"),("adaptive","dense"),("linked_dense","dense")]
    delta=np.stack([vals[:,names.index(a)]-vals[:,names.index(b)] for a,b in pairs],axis=1)
    samples=[]
    rng=np.random.default_rng(470091)
    for _ in range(100):
        idx=rng.integers(len(keys),size=(100,len(keys)))
        w=np.array([np.bincount(i,minlength=len(keys)) for i in idx])
        samples.append((w@delta.reshape(len(keys),-1)/len(keys)).reshape(-1,*delta.shape[1:]))
    ci=100*np.quantile(np.concatenate(samples),[.025,.975],axis=0)
    for j,(a,b) in enumerate(pairs):
        ds=delta[:,j,:]
        contrasts[a+"-"+b]=dict(pp=(100*ds.mean(0)).tolist(),ci=ci[:,j,:].T.tolist(),
              wins=(ds>1e-12).sum(0).tolist(),losses=(ds< -1e-12).sum(0).tolist())
    return dict(n=len(keys),columns=["em","f1","all_support_titles","mean_fraction_support"],
        means_pct={a:(100*vals[:,j].mean(0)).tolist() for j,a in enumerate(names)},paired=contrasts,
        primary_randomization=sign_p(delta[:,0,1]))


def main():
    check()
    inputs=get(P/"visible.json.gz");ctx=get(D/"contexts.json.gz");choices=get(D/"router-choices.json.gz")
    ans=get(D/"answers.json.gz");flags=get(D/"flags.json.gz")
    seals=get(D/"answer-seal.json")
    assert seals["answers"]==sha(D/"answers.json.gz") and seals["input"]==sha(D/"input-seal.json")
    assert get(D/"route-seal.json")["choices"]==sha(D/"router-choices.json.gz")
    assert len(ctx)==len(set(x["cluster"] for x in ctx.values()))==N
    assert set(inputs)==set(ctx)==set(choices)==set(flags)
    src={r["id"]:r for path in FILES for r in columns(path,["id","answer","type","supporting_facts"]) if r["id"] in ctx}
    assert len(src)==N
    evaluator=official()
    gold, rows, raw, refs={},{},[],{}
    for q in sorted(src):
        r=src[q]; c=ctx[q]; texts=inputs[q]
        titles=[x[1] for x in texts[1]]
        sup=set(r["supporting_facts"]["title"])
        truth=r["answer"]; chosen=choices[q]
        assert c["refs"][chosen["arm"]][0]==chosen["address"]
        rr=dict(c["refs"]);rr["router"]=rr[chosen["arm"]];refs[q]=rr
        scores={}
        for a,(i,k,L) in rr.items():
            found={titles[c["seed"]],titles[i]}
            scores[a]=[float(evaluator.exact_match_score(ans[k]["answer"],truth)),evaluator.f1_score(ans[k]["answer"],truth)[0],
                       int(sup<=found),len(sup&found)/len(sup)]
        raw.append(dict(_id=q,answer=truth,supporting_facts=list(zip(r["supporting_facts"]["title"],r["supporting_facts"]["sent_id"],strict=True))))
        gold[q]=dict(answer=truth,support_titles=sorted(sup),titles=titles,question=texts[0])
        rows[q]=dict(kind=r["type"],flag=flags[q],changed=rr["router"][0]!=rr["linked_dense"][0],cluster=c["cluster"],arms=scores)
    put(D/"gold.json.gz",gold);put(D/"outcomes.json.gz",rows)
    result=analyze(rows)
    result["outcomes"]=sha(D/"outcomes.json.gz")
    result["flags"]=dict(Counter(str(r["flag"])+"|"+r["kind"] for r in rows.values()))
    result["switched"]=sum(r["changed"] for r in rows.values())
    result["source_arms"]={a:sum(rr[a][0]!=rr["dense"][0] for rr in refs.values()) for a in next(iter(refs.values()))}
    result["strata"]={}
    for kind in sorted({r["kind"] for r in rows.values()}):
        subset=[r for r in rows.values() if r["kind"]==kind]
        result["strata"][kind]=dict(n=len(subset),means_pct={a:(100*np.mean([r["arms"][a] for r in subset],axis=0)).tolist() for a in rows[q]["arms"]})
    gp,pp=P/"official-gold.json",P/"official-pred.json"
    gp.write_text(json.dumps(raw,ensure_ascii=True),encoding="ascii")
    result["official"]={}
    for a in next(iter(refs.values())):
        pred={"answer":{q:ans[rr[a][1]]["answer"] for q,rr in refs.items()},"sp":{q:[] for q in refs}}
        pp.write_text(json.dumps(pred,ensure_ascii=True),encoding="ascii")
        cap=StringIO()
        with redirect_stdout(cap):evaluator.eval(str(pp),str(gp))
        metrics=ast.literal_eval(cap.getvalue())
        result["official"][a]={k:metrics[k] for k in ("em","f1")}
        assert all(abs(metrics[k]*100-result["means_pct"][a][i])<1e-9 for i,k in enumerate(("em","f1")))
    put(D/"results.json",result)
    print(result["means_pct"],result["paired"]["router-linked_dense"],result["primary_randomization"],flush=True)


if __name__=="__main__":
    main()
