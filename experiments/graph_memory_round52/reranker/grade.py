"""Score every frozen decision with the two benchmark authors' answer graders."""
import importlib.util
import math
import sys
import numpy as np
from reader import archive
from common import *

sys.path.insert(0,str(R51/"baseline"))
from study import ci_records
from verify import score
from grade_complete import module

PAIRS=[("ce_graph",a) for a in ("ce_hybrid","ce","ce_linked","linked_dense","dense","r51_graph")]+[
       ("ce","dense"),("ce_hybrid","r51_hybrid"),("ce_linked","linked_dense")]
GRADERS={"2wiki":(CACHE/"x20-r50-qa-external/author_evaluate.py","7c09ee2ec98c7ecb57df79eb68dba22eb381ab58d50e730dfcefafb4dda31458"),
         "hotpot":(CACHE/"x20-r51-hotpot-gate/official.py","d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0")}
METRICS=("full","recall","em","f1")
def signflip(ds):
    x=np.asarray(ds);w=np.abs(x[np.abs(x)>1e-12]);obs=abs(x.sum())
    rng=np.random.default_rng(510272)
    if len(w)<=20:
        vals=np.array([0.])
        for v in w:vals=np.r_[vals-v,vals+v]
        extreme=int((np.abs(vals)>=obs-1e-12).sum());draws=len(vals);p=extreme/draws
    else:
        extreme=0;draws=1_000_000
        for j in range(0,draws,1000):
            signs=rng.integers(0,2,size=(1000,len(w)),dtype=np.int8)*2-1
            extreme+=int((np.abs((signs*w).sum(axis=1))>=obs-1e-12).sum())
        p=(extreme+1)/(draws+1)
    return dict(p=float(p),draws=draws,extreme=extreme,nonzero=len(w),seed=510272)
def grade():
    ctx=get("contexts.json.gz");new=get("new-answers.json.gz")
    assert sha(D/"new-answers.json.gz")==get("answer-seal.json")["answers"]
    assert sha(D/"contexts.json.gz")==get("input-seal.json")["contexts"]
    known=archive()
    assert not set(new)&set(known) and all(v==known[k] for k,v in get("reader-replay.json").items())
    known.update(new);records={};result={}
    for p in EVAL:
        author=module(*GRADERS[p]);gold=read(PANELS[p][0]/"gold.json.gz");qs=sorted(gold)
        assert qs==sorted(ctx[p]) and len(qs)==1280
        assert len({r["cluster"] for r in ctx[p].values()})==len(qs)
        records[p]={}
        for q in qs:
            z=gold[q];c=ctx[p][q]; row={}
            if p=="2wiki":refs,titles,supp=z
            else:refs,titles,supp=[z["answer"]],z["titles"],z["support_titles"]
            supp=set(supp)
            for a,(i,k,_) in c["refs"].items():
                s=known[k]["answer"];em,f1=score(s,refs)
                if p=="hotpot":
                    em_off=author.exact_match_score(s,refs[0]);f1_off=author.f1_score(s,refs[0])[0]
                else:
                    out=dict(em=0.,f1=0.,prec=0.,recall=0.);author.update_answer(out,s,refs)
                    em_off,f1_off=out["em"],out["f1"]
                assert em==em_off and abs(f1-f1_off)<1e-12
                hits={titles[c["seed"]],titles[i]}&supp
                row[a]=dict(em=em,f1=f1,full=int(len(hits)==len(supp)),recall=len(hits)/len(supp))
            records[p][q]=row
        rec=records[p];arms=sorted(rec[qs[0]]);pol={}
        for a in arms:
            pol[a]={m:math.fsum(rec[q][a][m] for q in qs)/len(qs) for m in METRICS}
        features=[(a,b,m) for a,b in PAIRS for m in METRICS]
        arr=np.array([[rec[q][a][m]-rec[q][b][m] for a,b,m in features] for q in qs])
        est=ci_records(arr,np.random.default_rng(510271));comparisons={}
        for j,((a,b,m),(d,lo,hi)) in enumerate(zip(features,est)):
            x=arr[:,j];vals=dict(delta_pp=d,ci95_pp=[lo,hi],wins=int((x>1e-12).sum()),losses=int((x< -1e-12).sum()))
            if p=="hotpot" and (a,b,m)==("ce_graph","ce_hybrid","f1"):vals["signflip"]=signflip(x)
            comp=comparisons.setdefault(a+"-"+b,{"different_address":sum(ctx[p][q]["refs"][a][0]!=ctx[p][q]["refs"][b][0] for q in qs)})
            comp[m]=vals
        result[p]=dict(n=len(qs),shortened=sum(c["cap"]!=c["previous"] for c in ctx[p].values()),
                       unique_new_prompts=len({k for c in ctx[p].values() for _,k,_ in c["refs"].values() if k in new}),
                       policies=pol,contrasts=comparisons)
    put("records.json.gz",records);put("results.json",result)
    put("grade-seal.json",dict(records=sha(D/"records.json.gz"),results=sha(D/"results.json"),answers=sha(D/"answer-seal.json"),
        gold={p:sha(PANELS[p][0]/"gold.json.gz") for p in EVAL},graders={p:v[1] for p,v in GRADERS.items()},
        assignments=sum(v["n"]*len(v["policies"]) for v in result.values()),code=sha(Path(__file__))))
    print(json.dumps({p:v["contrasts"]["ce_graph-ce_hybrid"]["f1"] for p,v in result.items()}))
if __name__=="__main__":grade()
