"""Analyze the complete matched panels. Gold typing is used only after rankings were frozen."""
from pathlib import Path
import collections
import gzip
import json
import math
from statistics import mean
import numpy as np

BASE=Path(__file__).resolve().parent
def load(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)
def matched(left,right):
    assert set(left)==set(right)
    groups=collections.defaultdict(list)
    wins=losses=0
    for q,a in left.items():
        d=a["full_support"]-right[q]["full_support"]
        groups[a["trajectory"]].append(d)
        wins+=d>0;losses+=d<0
    vals=list(groups.values())
    sums=np.array([sum(v) for v in vals]);lens=np.array(list(map(len,vals)))
    rng=np.random.default_rng(13);ind=rng.integers(0,len(vals),size=(10000,len(vals)))
    ci=np.quantile(sums[ind].sum(axis=1)/lens[ind].sum(axis=1),[.025,.975])
    n=wins+losses
    p=min(1.,2*sum(math.comb(n,k) for k in range(min(wins,losses)+1))/2**n)
    return {"delta":float(sums.sum()/lens.sum()),"wins":wins,"losses":losses,"trajectories":len(vals),
            "exact_mcnemar_query_p":p,"trajectory_bootstrap_ci":[float(x) for x in ci]}
def summary(entries):
    return {"n":len(entries),"full":int(sum(r["full_support"] for r in entries)),
            **{m:mean(r[m] for r in entries) for m in ("coverage","density","f1","tokens","nodes")},
            "filled_fraction":mean(r["tokens"]/r["budget"] for r in entries)}
def analyze(folder):
    rows=load(folder/"outcomes.json.gz")
    labels=load(folder/"gold-spans.json.gz")
    classes={q:"both" if {v["json_pointer"] for v in spans}=={"/raw_arguments","/content"} else
               "argument" if {v["json_pointer"] for v in spans}=={"/raw_arguments"} else "output"
             for q,spans in labels.items()}
    assert all({v["json_pointer"] for v in span}<={"/raw_arguments","/content"} for span in labels.values())
    named=collections.defaultdict(dict)
    for r in rows:named[(r["budget"],r["view"],r["policy"])][r["query"]]=r
    contrasts={}
    for b in (512,1024,2048):
        for v in ("flat","provenance"):
            for treatment,control in [("skip","prefix"),("value","prefix"),("value","skip")]+([("related","skip"),("related","value")] if v=="provenance" else []):
                left=named[(b,v,treatment)];right=named[(b,v,control)]
                contrasts[f"{b}/{v}/{treatment}-{control}"]=matched(left,right)
    groups={c:sum(v==c for v in classes.values()) for c in ("both","argument","output")}
    strata={}
    for (b,view,policy),items in named.items():
        if b!=2048:continue
        strata[f"{view}/{policy}"]={c:summary([r for q,r in items.items() if classes[q]==c]) for c,n in groups.items() if n}
    metrics={"/".join(map(str,k)):summary(list(v.values())) for k,v in named.items()}
    return {"panels":metrics,"paired":contrasts,"posthoc_evidence_shapes":groups,"posthoc_outcomes_by_shape":strata}
if __name__=="__main__":
    results={"first":analyze(BASE),"replication":analyze(BASE/"replication")}
    a=load(BASE/"cohort.json")["selected"];b=load(BASE/"replication/cohort.json")["selected"]
    assert not set(a)&set(b)
    f=BASE/"paired-panels.json";f.write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    for p,s in results.items():
        print(p,s["posthoc_evidence_shapes"])
        for k,v in s["panels"].items():
            if k.startswith("2048/"):print(k,v["full"],round(v["coverage"],3),round(v["density"],3),round(v["tokens"],1),round(v["nodes"],1))
        print(s["paired"]["2048/provenance/related-value"])
