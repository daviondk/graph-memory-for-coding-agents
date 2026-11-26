from collections import Counter,defaultdict
import numpy as np
from shared import *
from grade import PAIRS

def pool(cases):
    by=defaultdict(list);write={m:Counter() for m in METHODS}
    for r in cases:
        by[r["issue"]].append(r)
        for m in METHODS:write[m].update(r["write"][m])
    groups=[g for _,g in sorted(by.items())];counts=np.array([len(g) for g in groups])
    rng=np.random.default_rng(434371);draw=rng.integers(len(groups),size=(10000,len(groups)))
    W=np.stack([np.bincount(d,minlength=len(groups)) for d in draw]);budgets={}
    for cap in map(str,BUDGETS):
        arms={m:Counter() for m in METHODS};pairs={}
        for r in cases:
            for m in METHODS:arms[m].update(r["metrics"][cap][m])
        for m,b in PAIRS:
            label=m+"_minus_"+b
            def delta(r):return r["metrics"][cap][m]["hit"]-r["metrics"][cap][b]["hit"]
            tot=np.array([sum(map(delta,g)) for g in groups]);macro=tot/counts
            pairs[label]=dict(delta=float(tot.sum()/len(cases)),macro=float(macro.mean()),
                ci=np.quantile((W@tot)/(W@counts),[.025,.975]).tolist(),
                macro_ci=np.quantile(W@macro/len(groups),[.025,.975]).tolist(),
                wins=sum(delta(r)>0 for r in cases),losses=sum(delta(r)<0 for r in cases),
                identification=[sum(r["bounds"][cap][label][i] for r in cases)/len(cases) for i in (0,1)])
        budgets[cap]=dict(methods=arms,contrasts=pairs)
    return dict(n=len(cases),issues=len(groups),closed=sum(r["closed"] for r in cases),view_count=sum(r["views"] for r in cases),
                novel_rows=sum(r["novel_demand"] for r in cases),successful_full_rebase=sum(r["rebase_succeeded"] for r in cases),
                write=write,budgets=budgets)


def main():
    o=read(D/"outcomes.json.gz");assert sha(D/"outcomes.json.gz")==read(D/"grade-seal.json")["outcomes"]
    panels={}
    for name,p in (("held1071",lambda r:r["held"]),("all2696",lambda r:True),("main676",lambda r:r["group"]=="main"),
                   ("held_closed",lambda r:r["held"] and r["closed"]),("held_observed",lambda r:r["held"] and r["views"]),
                   ("held_no_literal",lambda r:r["held"] and not r["rebase_succeeded"])):
        rows=[r for r in o.values() if p(r)]
        if rows:panels[name]=pool(rows)
    save("results.json",dict(panels=panels,primary="held1071/2048/boundary_minus_rebase/issue_macro",
        safety_audit="all2696/wrong_candidate,bad_emitted",bootstrap={"unit":"issue","seed":434371,"reps":10000},
        source=sha(D/"grade-seal.json")))
    for n,t in panels.items():
        print(n,t["n"],{m:[x["hit"],x.get("lines",0),x["bad_emitted"]] for m,x in t["budgets"]["2048"]["methods"].items()})
if __name__=="__main__":main()

