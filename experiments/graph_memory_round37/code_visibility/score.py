"""All outcomes refer to addresses actually visible at the independent next read."""
from predict import D,get,save,sha,ALG
from collections import Counter,defaultdict
import numpy as np

def tally(p,gold):
    target=dict(gold)
    pred=dict(p)
    verified=sum(n in target for n in pred)
    correct=sum(target.get(n)==sig for n,sig in pred.items())
    return np.array([len(target),correct,verified-correct,len(pred)],int)

def summarize(group):
    if not group:return {}
    issues=sorted({r["issue"] for r in group});repos=sorted({r["repo"] for r in group})
    mat=np.zeros((len(issues),len(ALG),4),dtype=int)
    for r in group:
        for m,x in r["metrics"].items():mat[issues.index(r["issue"]),ALG.index(m)]+=x
    macro=mat[:,:,1:3]/mat[:,:,0,None]
    summary={}
    for j,m in enumerate(ALG):
        n,c,w,cost=map(int,mat[:,j,:].sum(0));summary[m]=dict(observed=n,correct=c,wrong=w,unchecked=cost-c-w,
             coverage=float(macro[:,j,0].mean()),stale=float(macro[:,j,1].mean()),precision_pooled=c/(c+w) if c+w else None,
             fact_slots_per_episode=cost/len(group))
    rng=np.random.default_rng(370153);idx=rng.integers(len(issues),size=(10000,len(issues)))
    contrasts={}
    for a,b in (("T","F"),("T","K"),("Tstar","H"),("T","U")):
        delta=macro[:,ALG.index(a),:]-macro[:,ALG.index(b),:];dist=delta[idx].mean(1)
        comparisons={}
        for k,label in enumerate(("coverage","stale")):
            comparisons[label]=dict(delta=float(delta[:,k].mean()),ci95=np.quantile(dist[:,k],[.025,.975]).tolist())
        contrasts[a+"-"+b]=comparisons
    aa=[r["native_audit"] for r in group if r["anchor"] is not None]
    return dict(episodes=len(group),issues=len(issues),repos=len(repos),runs=len({r["rid"] for r in group}),anchored=len(aa),
        native_verified=sum(r["native_audit"]["native_full_verified"] for r in group),anchors_independently_auditable=sum(a["native_full_verified"] for a in aa),
        anchor_agree=sum(a["native_anchor_agrees"] is True for a in aa),anchor_disagree=sum(a["native_anchor_agrees"] is False for a in aa),
        positive_delta=sum(r["delta"]>0 for r in group),negative_delta=sum(r["delta"]<0 for r in group),methods=summary,contrasts=contrasts)

def main():
    sealed=get(D/"prediction-seal.json");pred=get(D/"predictions.json.gz");truth=get(D/"observations.json.gz")
    assert sha(D/"predictions.json.gz")==sealed["predictions"] and sha(D/"observations.json.gz")==sealed["observations"]
    assert {p["q"] for p in pred}==set(truth)
    out=[]
    for p in pred:
        t=truth[p["q"]];g=t["observed"];assert g and [v[0] for v in g]==sorted({v[0] for v in g})
        m={name:tally(p["mem"][name],g).tolist() for name in ALG}
        assert m["Tstar"][3]==m["H"][3]
        out.append({**{k:v for k,v in p.items() if k!="mem"},"metrics":m,"native_audit":t["native_audit"]})
    counts={}
    for co in ("main","secondary"):
        for w in ("strict","opaque"):
            subset=[r for r in out if r["cohort"]==co and r["window"]==w]
            counts[co+"_"+w]=summarize(subset)
            counts[co+"_"+w+"_shift"]=summarize([r for r in subset if r["delta"]!=0])
    first=[r for r in out if r["cohort"]=="main" and r["window"]=="strict"]
    repos=sorted({r["repo"] for r in first})
    perrepo={k:summarize([r for r in first if r["repo"]==k]) for k in repos}
    leave={k:summarize([r for r in first if r["repo"]!=k])["contrasts"] for k in repos} if len(repos)>1 else {}
    seal=save(D/"outcomes.json.gz",out)
    result=dict(groups=counts,repo=perrepo,leave_one_repo=leave,scored=seal,forecast_seal=sha(D/"prediction-seal.json"))
    save(D/"results.json",result)
    for k,v in counts.items():
        if not v:continue
        print(k,v["episodes"],v["issues"],v["repos"],v["anchored"],v["anchor_agree"],v["anchor_disagree"],
              [(a,round(w["coverage"]*100,2),round(w["stale"]*100,2),w["correct"],w["wrong"]) for a,w in v["methods"].items()])
    print(counts["main_strict"]["contrasts"])
if __name__=="__main__":main()
