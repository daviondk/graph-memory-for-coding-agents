from collections import Counter,defaultdict
import numpy as np
from data import D,METHODS,read,save,sha
from score import PAIRS


def describe(part):
    by=defaultdict(list);arms={m:Counter() for m in METHODS};demand=Counter();stops=Counter()
    for r in part:
        by[r["issue"]].append(r);demand.update(r["demand"]);stops[r["stop"]]+=1
        for m in METHODS:arms[m].update(r["arms"][m])
    gs=[by[q] for q in sorted(by)];sizes=np.array([len(g) for g in gs])
    rng=np.random.default_rng(42707);W=np.stack([np.bincount(a,minlength=len(gs)) for a in rng.integers(len(gs),size=(10000,len(gs)))])
    cmp={}
    for m,b in PAIRS:
        name=m+"_minus_"+b
        net=np.array([sum(x["arms"][m]["hit"]-x["arms"][b]["hit"] for x in g) for g in gs]);macro=net/sizes
        bounds={lab:sum(x["bounds"][name][j] for x in part)/len(part) for j,lab in enumerate(("lower","upper"))}
        macrob={lab:float(np.mean([sum(x["bounds"][name][j] for x in g)/len(g) for g in gs])) for j,lab in enumerate(("lower","upper"))}
        cmp[name]=dict(delta=float(net.sum()/len(part)),macro=float(macro.mean()),
           ci=np.quantile((W@net)/(W@sizes),[.025,.975]).tolist(),macro_ci=np.quantile((W@macro)/len(gs),[.025,.975]).tolist(),
           wins=sum(x["arms"][m]["hit"]>x["arms"][b]["hit"] for x in part),
           losses=sum(x["arms"][m]["hit"]<x["arms"][b]["hit"] for x in part),
           identification=bounds,macro_identification=macrob)
    return dict(episodes=len(part),issues=len(gs),repos=len({r["repo"] for r in part}),demand=demand,
                methods=arms,stops=stops,contrasts=cmp)


def main():
    o=read(D/"outcomes.json.gz");assert sha(D/"outcomes.json.gz")==read(D/"score-seal.json")["outcomes"]
    panels={}
    criteria=(("held1071",lambda x:x["held"]),("all2696",lambda x:True),("main676",lambda x:x["group"]=="main"),
              ("held_closed",lambda x:x["held"] and x["demand"]["closed"]),("all_closed",lambda x:x["demand"]["closed"]),
              ("held_demand",lambda x:x["held"] and x["demand"]["observed_demand"]),
              ("held_novel_demand",lambda x:x["held"] and x["demand"]["observed_novel"]),
              ("held_censored",lambda x:x["held"] and x["demand"]["censored"]))
    for name,fn in criteria:
        pp=[r for r in o.values() if fn(r)]
        if pp:panels[name]=describe(pp)
    save("results.json",dict(panels=panels,primary="held1071/local_minus_range/hit/issue_macro",
        bootstrap={"seed":42707,"replicates":10000,"unit":"issue"},source=sha(D/"score-seal.json")))
    for n,z in panels.items():
        print(n,z["episodes"],z["demand"].get("views",0),{m:[a.get("hit",0),a.get("novel_lines",0)] for m,a in z["methods"].items()})
if __name__=="__main__":main()

