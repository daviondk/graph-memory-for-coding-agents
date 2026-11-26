"""Compute paired decomposition on fixed, re-priced prompts; all metrics remain per question."""
from common import D,BASE,DATA,raw,digest,put,source,ci_records
from verify import score
from grade_complete import module
from pathlib import Path
import math
import sys
import numpy as np
sys.path.append(str(BASE/"confirm"))
from driver import signflip

MODES=("graph","masked","hybrid")
CONTRASTS=(("graph","masked"),("masked","hybrid"),("graph","hybrid"))

def main():
    seal=raw(D/"answer-seal.json")
    assert digest(D/"new-answers.json.gz")==seal["answers"] and digest(D/"input-seal.json")==seal["inputs"]
    new=raw(D/"new-answers.json.gz");ctx=raw(D/"contexts.json.gz")
    two=module(Path("D:/CodexResearch/x20-r50-qa-external/author_evaluate.py"),"7c09ee2ec98c7ecb57df79eb68dba22eb381ab58d50e730dfcefafb4dda31458")
    hot=module(Path("D:/CodexResearch/x20-r51-hotpot-gate/official.py"),"d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0")
    receipts={};results={}
    for p,(path,_) in DATA.items():
        _,_,_,extra=source(p)
        answers={**raw(path/"answers.json.gz"),**extra,**new}
        gold=raw(path/"gold.json.gz");panel=ctx[p];records={}
        assert len(panel)==1280==len({r["cluster"] for r in panel.values()})
        for q,row in panel.items():
            if p=="2wiki":refs,titles,support=gold[q]
            else:
                g=gold[q];refs=[g["answer"]];titles=g["titles"];support=g["support_titles"]
            support=set(support);record={}
            for a,(i,k,L) in row["refs"].items():
                ans=answers[k]["answer"];em,f1=score(ans,refs)
                seen={titles[row["seed"]],titles[i]}
                if p=="2wiki":
                    stat=dict(em=0.,f1=0.,prec=0.,recall=0.);two.update_answer(stat,ans,refs)
                    assert stat["em"]==em and abs(stat["f1"]-f1)<1e-12
                else:
                    assert hot.exact_match_score(ans,refs[0])==em and abs(hot.f1_score(ans,refs[0])[0]-f1)<1e-12
                record[a]={"f1":f1,"em":em,"full":int(support<=seen),"recall":len(support&seen)/len(support)}
            assert row["edge"] or row["refs"]["graph"]==row["refs"]["masked"]
            records[q]=record
        receipts[p]=records
        split={"all":sorted(panel),"edge":sorted(q for q,r in panel.items() if r["edge"]),
               "no_edge":sorted(q for q,r in panel.items() if not r["edge"])}
        stats={}
        for st,qs in split.items():
            n=len(qs);metrics=("f1","full","em","recall")
            scores={a:{m:math.fsum(records[q][a][m] for q in qs)/n for m in metrics} for a in MODES}
            keys=[];diffs=[];con={}
            for a,b in CONTRASTS:
                tag=a+"-"+b
                con[tag]={"switches":sum(panel[q]["refs"][a][0]!=panel[q]["refs"][b][0] for q in qs)}
                for m in metrics:
                    keys.append((tag,m));diffs.append([records[q][a][m]-records[q][b][m] for q in qs])
            cis=ci_records(np.array(diffs).T,np.random.default_rng(510812))
            for (tag,m),ds,val in zip(keys,diffs,cis):
                con[tag][m]={"delta_pp":val[0],"ci95_pp":val[1:],"gains":sum(v>1e-12 for v in ds),"losses":sum(v< -1e-12 for v in ds)}
                if (p,st,tag,m)==("hotpot","all","graph-masked","f1"):
                    con[tag][m]["sign_flip"]=signflip(ds)
            for m in metrics:
                assert abs(con["graph-masked"][m]["delta_pp"]+con["masked-hybrid"][m]["delta_pp"]-con["graph-hybrid"][m]["delta_pp"])<1e-12
            stats[st]={"n":n,"policies":scores,"contrasts":con}
        new_keys={k for r in panel.values() for i,k,L in r["refs"].values() if k in new}
        results[p]={"strata":stats,"new":len(new_keys),"shortened":{q:[v["original"],v["cap"]] for q,v in panel.items() if v["original"]!=v["cap"]}}
    put("outcomes.json.gz",receipts);put("results.json",results)
    put("grade-seal.json",{"results":digest(D/"results.json"),"outcomes":digest(D/"outcomes.json.gz"),
                          "answer":digest(D/"answer-seal.json"),"n":7680,
                          "official":["7c09ee2ec98c7ecb57df79eb68dba22eb381ab58d50e730dfcefafb4dda31458","d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0"]})
    print("Officially scored 7680 equal-budget cases.")
if __name__=="__main__":main()
