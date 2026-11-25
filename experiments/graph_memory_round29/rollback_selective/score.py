"""Isolated, post-seal scorer using the original claim evaluator and gold source/derived/benign IDs."""
from collections import defaultdict
import warnings
from hashlib import sha256
import numpy as np
from project import OUT,PRIV,SRC,get,save,readl
import sys
sys.path.insert(0,str(SRC))
from eval.metrics import _claim_metric,_affected_claim_ids
from eval.ground_truth import load_ground_truth_index
COL=["tp","fp","fn","source_hit","source_n","derived_hit","derived_n","benign_hit","benign_n"]
def rat(a,b):
    return np.divide(a,b,out=np.full(np.shape(a),np.nan,dtype=float),where=b!=0)
def metrics(s):
    tp,fp,fn=s[...,0],s[...,1],s[...,2]
    return dict(precision=rat(tp,tp+fp),recall=rat(tp,tp+fn),micro=rat(2*tp,2*tp+fp+fn),source_recall=rat(s[...,3],s[...,4]),derived_recall=rat(s[...,5],s[...,6]),benign_false_positive_rate=rat(s[...,7],s[...,8]))
def val(x):return float(x) if np.isfinite(x) else None
def interval(v):
    v=v[np.isfinite(v)]
    return [float(z) for z in np.quantile(v,[.025,.975])] if len(v) else None
def summary(ex):
    totals=ex.sum(0);o={k:val(v) for k,v in metrics(totals).items()};o.update(dict(zip(COL,map(int,totals))))
    f=metrics(ex)["micro"];good=f[np.isfinite(f)]
    o.update(macro_defined=float(good.mean()) if len(good) else None,n_defined=len(good),macro_zero=float(np.nan_to_num(f).mean()),macro_exact_empty=float(np.nan_to_num(f,nan=1.).mean()))
    return o
def main(p):
    sealed=get(OUT/"forecast-seal.json");assert all(sealed[k]==sha256((OUT/(k+"-forecasts.json.gz")).read_bytes()).hexdigest() for k in ["controlled","adapted"])
    root=SRC/"data"/("controlled_benchmark" if p=="controlled" else "adapted_lmev2_subset")
    reg={r["task_id"]:r for r in readl(root/"registry.jsonl")};key={r["id"]:r for r in get(PRIV/(p+"-evaluation-key.json.gz"))};golds={};cases=[]
    original={r["task"]:r for r in get(OUT.parent/"rollback_native"/(p+"-per-case.json.gz"))}
    for r in get(OUT/(p+"-forecasts.json.gz")):
        keyr=key[r["id"]];t=keyr["task"];d=keyr["domain"];m=reg[t];path=root/d/"ground_truth.jsonl"
        if d not in golds:golds[d]=load_ground_truth_index(path)
        truth=golds[d][t];claim=set(_affected_claim_ids(truth,dict(domain=d,task_id=t,fault_types=m["fault_types"]),None,path));gt=truth["memory_ground_truth"]
        assert claim==set(original[t]["gold_claims"])
        ms,md,mb=[set(gt[k]) for k in ["source_faulty_memories","derived_faulty_memories","benign_active_memory_ids"]];arms={}
        for a,res in r["arms"].items():
            kept={keyr["node"][i] for i in res["m"]};found={keyr["node"][i] for i in res["c"]};official=_claim_metric(claim,found);counts=[official[k] for k in COL[:3]]+[len(ms&kept),len(ms),len(md&kept),len(md),len(mb&kept),len(mb)]
            if a in ("reach","direct"):
                prior=original[t]["arms"]["reach_any" if a=="reach" else "direct"]
                assert counts[:3]==[prior[k] for k in COL[:3]] and counts[7]==prior["benign_total"]-prior["benign_retained"]
            arms[a]=counts
        cases.append(dict(id=r["id"],domain=d,fault="+".join(sorted(m["fault_types"])),arms=arms))
    grouped={v:np.array([i for i,r in enumerate(cases) if r["domain"]==v]) for v in sorted({c["domain"] for c in cases})}
    rng=np.random.default_rng(29030);draw=np.hstack([rng.choice(ii,(10000,len(ii))) for ii in grouped.values()])
    byfault={v:np.array([i for i,r in enumerate(cases) if r["fault"]==v]) for v in sorted({r["fault"] for r in cases})}
    reps={};res={}
    for a in cases[0]["arms"]:
        arr=np.array([r["arms"][a] for r in cases]);allmetrics=metrics(arr[draw].sum(1));pc=metrics(arr)["micro"];sample=pc[draw]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore",RuntimeWarning)
            allmetrics["macro_defined"]=np.nanmean(sample,axis=1)
        for n,v in [("macro_zero",0.),("macro_exact_empty",1.)]:allmetrics[n]=np.nan_to_num(sample,nan=v).mean(1)
        reps[a]=allmetrics
        res[a]=dict(summary=summary(arr),ci={k:interval(v) for k,v in allmetrics.items()},domain={d:summary(arr[ii]) for d,ii in grouped.items()},fault={d:summary(arr[ii]) for d,ii in byfault.items()})
    pairs={}
    for name,rp in reps.items():
        if name=="selective":continue
        pairs[name]={k:dict(delta=float(res["selective"]["summary"][k]-res[name]["summary"][k]),ci=interval(reps["selective"][k]-rp[k])) for k in ("micro","macro_defined","macro_zero","macro_exact_empty")}
    out=dict(n=len(cases),cases=save(OUT/(p+"-per-case.json.gz"),cases),fields=COL,arms=res,selective_minus=pairs)
    save(OUT/(p+"-results.json"),out)
    print(p,[(k,round(v["summary"]["micro"],3) if v["summary"]["micro"] is not None else None,round(v["summary"]["macro_defined"],3)) for k,v in res.items()])
if __name__=="__main__":
    for p in ["controlled","adapted"]:main(p)

