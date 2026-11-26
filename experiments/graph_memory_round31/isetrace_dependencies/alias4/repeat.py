"""Rerun fixed methods only on newly eligible sessions and changed record histories from the four-alias inventory."""
from pathlib import Path
from unittest.mock import patch
from collections import defaultdict,Counter
import sys
import numpy as np
D=Path(__file__).resolve().parent;main=D.parent
sys.path.insert(0,str(main))
import prepare as prep
import study
from prepare import read,save,sha
P=Path("D:/CodexResearch/x20-r31-isetrace-dependencies-alias4")
SRC=Path("D:/CodexResearch/x20-r30-witness/ise4-events.json.gz")
def cohort():
    old=prep.cohort();records=read(SRC);new={};types={}
    for r in records:
        q=r["id"];events=r["events"];idx=defaultdict(set)
        for j,e in enumerate(events):
            for line,digest,_ in e["lines"]:idx[e["path"],line,digest].add(j)
        overlap=any(len(x)>1 for x in idx.values())
        if not overlap and len(events)<3:continue
        group=("overlap3" if len(events)>=3 else "overlap2") if overlap else "disjoint3"
        if q not in old:status="new"
        elif old[q][1]!=events:status="updated"
        else:continue
        new[q]=(group,events);types[q]=status
    c=Counter(new[q][0] for q in new if types[q]=="new")
    assert c=={"overlap3":11,"overlap2":2,"disjoint3":19}
    return new,types

def mainfn():
    new,types=cohort();plan={"ids":types,"raw_audit":sha(SRC),"old_plan":sha(main/"plan.json"),"protocol":sha(D/"PROTOCOL_RU.md"),"script":sha(Path(__file__))}
    if (D/"extension-plan.json").exists():assert read(D/"extension-plan.json")==plan
    else:save(D/"extension-plan.json",plan)
    with patch.multiple(prep,D=D,P=P,WHOLE=SRC,cohort=lambda:new):prep.make()
    with patch.multiple(study,D=D,P=P):study.build()
    rows=read(D/"per-session.json.gz");out={}
    for classification in ("new","updated"):
        for group in ("overlap3","overlap2","disjoint3"):
            ids=sorted(q for q in rows if types[q]==classification and new[q][0]==group)
            if not ids:continue
            delta={}
            for comparison in ("raw","producer","atom_group","mask_group"):
                totals=np.array([[rows[q]["line_bm25"]["counts"][m+"4"]["sampled"][0] for m in ("mask_pareto",comparison)] for q in ids])
                rate=(totals[:,0]-totals[:,1])/64
                rng=np.random.default_rng(31203);boot=rate[rng.integers(len(ids),size=(10000,len(ids)))].mean(axis=1)
                delta[comparison]={"certified":totals.sum(axis=0).tolist(),"pp":100*float(rate.mean()),"ci":np.percentile(100*boot,[2.5,97.5]).tolist(),
                                   "better_sessions":int(sum(rate>0)),"worse_sessions":int(sum(rate<0))}
            out[classification+"/"+group]={"sessions":len(ids),"cases":64*len(ids),"comparisons":delta}
    save(D/"extension-results.json",{"source":sha(D/"source-seal.json"),"results":sha(D/"result-seal.json"),"extension":sha(D/"extension-plan.json"),"estimates":out})
    print(out.get("new/overlap3"))
if __name__=="__main__":mainfn()
