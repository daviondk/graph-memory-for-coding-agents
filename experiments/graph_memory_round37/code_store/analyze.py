"""Paired interval on ratios of sums with issue clusters and fixed episode multiplicity."""
from inputs import D,get,put,sha
from collections import defaultdict,Counter
import numpy as np
METHODS="AML"
def metrics(Y):
    ids=sorted(Y)
    out={}
    for m in METHODS:
        s=Counter()
        for q in ids:s.update(Y[q][m])
        out[m]=dict(s)
    return out

def cluster_effect(a,b,issues):
    labs=sorted(set(issues));ag=np.array([a[np.array(issues)==i].sum() for i in labs]);bg=np.array([b[np.array(issues)==i].sum() for i in labs])
    rng=np.random.default_rng(371542);draw=rng.integers(len(labs),size=(10000,len(labs)))
    boot=ag[draw].sum(1)/bg[draw].sum(1)
    return dict(ratio=float(ag.sum()/bg.sum()),ci95=np.quantile(boot,[.025,.975]).tolist(),units=len(issues),clusters=len(labs),
       fewer=sum(map(int,a<b)),tied=sum(map(int,a==b)))

def analyze():
    plan=get(D/"plan.json");seal=get(D/"run-seal.json");full=get(D/"full_counts.json.gz");timed=get(D/"timings.json.gz");inputs=get(D/"prefix_inputs.json.gz")
    assert seal["plan"]==sha(D/"plan.json") and sha(D/"timings.json.gz")==seal["timed"] and sha(D/"full_counts.json.gz")==seal["full"]
    assert set(full)==set(inputs) and set(timed)==set(plan["panel"])
    grouped={k:metrics({q:v for q,v in full.items() if inputs[q]["zone"]==k}) for k in sorted({v["zone"] for v in inputs.values()})}
    ids=sorted(full);groups=[inputs[q]["issue"] for q in ids]
    cnt={}
    for key in ("writes","wal_frames","read_rows"):
        vals={m:np.array([full[q][m][key] for q in ids]) for m in METHODS}
        cnt[key]={l+"/"+r:cluster_effect(vals[l],vals[r],groups) for l,r in (("L","M"),("L","A"),("M","A"))}
    panel=plan["panel"];issues=[inputs[q]["issue"] for q in panel];ck={};absval={}
    X=np.array([[[rep[m] for m in METHODS] for rep in timed[q]] for q in panel]);assert X.shape==(128,6,3,6)
    x=X.mean(1)
    for off,clock in ((0,"wall_ns"),(3,"cycles")):
        c={};av={}
        for k,positions in (("update",(0,)),("first_read",(1,)),("update_first",(0,1)),("update_four",(0,1,2))):
            sub=x[:,:,[off+i for i in positions]].sum(2)
            c[k]={a+"/"+b:cluster_effect(sub[:,METHODS.index(a)],sub[:,METHODS.index(b)],issues) for a,b in (("L","M"),("L","A"),("M","A"))}
            av[k]={m:dict(mean=float(sub[:,j].mean()),median=float(np.median(sub[:,j])),p95=float(np.quantile(sub[:,j],.95))) for j,m in enumerate(METHODS)}
        ck[clock]=c;absval[clock]=av
    out=dict(totals=metrics(full),grouped=grouped,count_ratios=cnt,timing_ratios=ck,times=absval,clock_panel_by_zone=Counter(inputs[q]["zone"] for q in panel),
        full_issues=len(set(groups)),timed_issues=len(set(issues)),full=len(ids),timed=len(panel))
    put(D/"results.json",out)
    return out
if __name__=="__main__":
    out=analyze()
    for k,v in out["timing_ratios"]["wall_ns"].items():print(k,v)
    print("writes",out["count_ratios"]["writes"])
