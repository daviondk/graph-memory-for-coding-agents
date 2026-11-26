"""Evaluate frozen decisions on previous paired costs and freshly executed robust routing."""
from features import *
from model import probability
import numpy as np
from scipy.stats import rankdata
def auc(p,y):
    p=np.asarray(p,float);y=np.asarray(y,bool);a=int(y.sum());b=len(y)-a
    return float((rankdata(p)[y].sum()-a*(a+1)/2)/(a*b)) if a and b else None
def paired(a,b,lab):
    names=sorted(set(lab));a=np.asarray(a);b=np.asarray(b);lab=np.asarray(lab)
    x=np.array([a[lab==k].sum() for k in names]);y=np.array([b[lab==k].sum() for k in names])
    ix=np.random.default_rng(371903).integers(len(x),size=(10000,len(x)));xx=x[ix].sum(1);yy=y[ix].sum(1)
    return dict(ratio=float(x.sum()/y.sum()),ci95=np.quantile(xx/yy,[.025,.975]).tolist(),groups=len(names))
def rates(vals,y):
    x=np.asarray(vals);labels=np.asarray(y,bool)
    return dict(n=len(y),zeros=int(labels.sum()),brier=float(np.mean((x-labels.astype(float))**2)),auc=auc(x,labels),
                pred_mean=float(x.mean()),pred_range=[float(x.min()),float(x.max())])
def section(cost,qs,meta,label="H"):
    rep=[meta[q]["repo"] for q in qs];issue=[meta[q]["issue"] for q in qs];n=len(qs)
    vals={m:np.array([cost[q][m] for q in qs]) for m in cost[qs[0]]}
    out=dict(n=n,means_ns={m:float(x.mean()) for m,x in vals.items()},contrast={})
    for m in ("A","L","const","chosen_bare"):
        if m in vals:
            a,b=vals[label],vals[m]
            out["contrast"][m]=dict(repo=paired(a,b,rep),issue=paired(a,b,issue),micro_diff_ns=float((a-b).mean()),
               repo_equal_mean_ratio=float(np.mean([a[np.array(rep)==r].mean()/b[np.array(rep)==r].mean() for r in set(rep)])))
    oracle=np.minimum(vals["A"],vals["L"]);c=vals["const"];best=min(vals["A"].sum(),vals["L"].sum())
    out.update(oracle_ns=float(oracle.mean()),oracle_gap_recovered=float((c.sum()-vals["H"].sum())/(c.sum()-oracle.sum())),
       best_constant_gap_recovered=float((best-vals["H"].sum())/(best-oracle.sum())),posthoc_regret_ns=float((vals["H"]-oracle).mean()))
    out["per_repo"]={}
    for r in sorted(set(rep)):
        mask=np.array(rep)==r
        out["per_repo"][r]=dict(n=int(mask.sum()),means_ns={m:float(x[mask].mean()) for m,x in vals.items()},oracle_ns=float(oracle[mask].mean()))
    return out
def main():
    dec=get(D/"decisions.json.gz");mod=get(D/"models.json");feat=get(D/"features.json.gz");live=get(D/"live-timings.json.gz")
    old=get(P/"physical.json.gz")["observed"];fu={r["q"]:r for r in get(P/"followup.json.gz")};pan=get(P/"physical-plan.json")["panel"]
    costs={};measured={};cpu={}
    for q in pan:
        a={m:float(np.mean([rep[m][0]+rep[m][1] for rep in old[q]])) for m in "AL"}
        costs[q]=a|{m:a[dec[q][m]] for m in ("H","J","const")}
        for ledger,j in ((measured,0),(cpu,2)):
            b={m:float(np.mean([r[m][j]+r[m][j+1] for r in live[q]])) for m in "ALH"}
            ledger[q]=b|dict(const=b[dec[q]["const"]],chosen_bare=b[dec[q]["H"]],J=b[dec[q]["J"]])
    final=dict(offline=section(costs,pan,fu),live=section(measured,pan,fu),cycles=section(cpu,pan,fu))
    proba={q:(probability(mod[r["repo"]]["logistic"],feat[q]),mod[r["repo"]]["train_zero_probability"]) for q,r in fu.items() if r["prefix"]=="clean"}
    complete=[q for q in proba if fu[q]["strict"]["stop"] in ("mutation","finished")]
    complete_set=set(complete)
    known=[q for q in proba if q in complete_set or fu[q]["strict"]["reads"]>0]
    knownset=set(known);unknown=[q for q in proba if q not in knownset]
    demand={}
    for name,keys in (("timed",pan),("complete",complete),("known",known)):
        y=[fu[q]["strict"]["reads"]==0 for q in keys];x=[proba[q][0] for q in keys];base=[proba[q][1] for q in keys]
        here=dict(model=rates(x,y),train_rate=rates(base,y))
        here["per_repo"]={}
        for repo in sorted(mod):
            sub=[q for q in keys if fu[q]["repo"]==repo]
            here["per_repo"][repo]=rates([proba[q][0] for q in sub],[fu[q]["strict"]["reads"]==0 for q in sub])
        demand[name]=here
    y=np.array([fu[q]["strict"]["reads"]==0 for q in known],float);a=np.array([proba[q][0] for q in known]);b=np.array([proba[q][0] for q in unknown])
    fixed=np.square(a-y).sum()
    demand["unidentified_clean"]=len(unknown)
    demand["brier_identification_bounds_all_clean"]=[float((fixed+f(b*b,(1-b)**2).sum())/len(proba)) for f in (np.minimum,np.maximum)]
    final["demand"]=demand
    final["choices"]={m:dict(Counter(dec[q][m] for q in pan)) for m in ("H","J","const")}
    final["choices_by_repo"]={r:dict(Counter(dec[q]["H"] for q in pan if fu[q]["repo"]==r)) for r in mod}
    final["beta_per_sd"]={r:dict(zip(NAMES,(np.array(m["ridge"]["coef"])*np.array(m["ridge"]["train_scale"])).tolist())) for r,m in mod.items()}
    put(D/"paired.json.gz",dict(offline=costs,live=measured,cycles=cpu))
    put(D/"results.json",final)
    print("offline",final["offline"]["contrast"]);print("live",final["live"]["contrast"])
if __name__=="__main__":main()
