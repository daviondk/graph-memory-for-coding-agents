"""Audit sealed forecasts independently against gold and original source, including identifier invariance."""
from collections import Counter
from hashlib import sha256
from math import isclose,exp
from pathlib import Path
from statistics import mean
from project import OUT,PRIV,PRE,get,save
from features import extract
import numpy as np

def rekey(row):
    f=lambda k:sha256(("verify opaque"+k).encode()).hexdigest()[:30]
    new={"id":f(row["id"]),"diagnosis":[f(a) for a in row["diagnosis"]],"memory":[],"steps":[]}
    for k in ("memory","steps"):
        for x in row[k]:
            y=dict(x);y["id"]=f(x["id"]);y["parents"]=[f(v) for v in x["parents"]]
            if "writes" in x:y["writes"]=[f(v) for v in x["writes"]]
            new[k].append(y)
    a,b=extract(row),extract(new)
    assert [f(x) for x in a["order"]]==b["order"]
    for u in a["order"]:assert a["features"][u]==b["features"][f(u)] and {f(v) for v in a["pathmem"][u]}==set(b["pathmem"][f(u)])
def main():
    seal=get(OUT/"forecast-seal.json");fits=get(OUT/"fits.json.gz");receipt={};dom=get(PRIV/"controlled-folds.json");assert len(dom)==150
    allcase=set(dom)|set(get(PRIV/"adapted-folds.json"));assert len(allcase)==200
    for p in ("controlled","adapted"):
        pred=get(OUT/(p+"-forecasts.json.gz"));res=get(OUT/(p+"-results.json"));raw=get(PRIV/(p+"-blind.json.gz"));fea={r["id"]:r for r in get(PRIV/(p+"-features.json.gz"))};key={r["id"]:r for r in get(PRIV/(p+"-evaluation-key.json.gz"))}
        previous={r["task"]:r["gold_claims"] for r in get(PRE/(p+"-per-case.json.gz"))}
        assert sha256((OUT/(p+"-forecasts.json.gz")).read_bytes()).hexdigest()==seal[p]
        for row in raw:rekey(row)
        card=Counter();rank=Counter();last_age=Counter();meangood={};counts=Counter();methods=pred[0]["arms"];pairs={a:[] for a in methods}
        for r in pred:
            q=r["id"];f=fea[q];k=key[q];task=k["task"];mp=k["node"];inv={v:u for u,v in mp.items()};truth={inv[x] for x in previous[task]}
            card[len(truth)]+=1
            if truth:
                rank["cases_with_any"]+=1
                rank["suffix_given_gold_count"]+=truth==set(f["order"][-len(truth):])
                rank["all_truth_is_last"]+=truth==set(f["order"][-1:])
                rank["last_is_true"]+=bool(truth&set(f["order"][-1:]))
                rank["gold_earlier_than_last_candidate"]+=len(truth&set(f["order"][:-1]))
                rank["gold_never_reachable"]+=len(truth-set(f["order"]))
            for i,u in enumerate(reversed(f["order"])):last_age[i]+=int(u in truth)
            for a,out in r["arms"].items():
                ids=set(out["c"]);tp=len(ids&truth);fp=len(ids-truth);fn=len(truth-ids)
                pairs[a].append((tp,fp,fn))
                if a in ("selective","position","graph","graph_pos","lexical"):
                    par=fits[r["fold"]][a];expected={v for v,e in dom.items() if e!=r["fold"]};assert set(par["train_ids"])==expected and q in par["heldout"] and q not in par["train_ids"]
                    calc=set()
                    for u in f["order"]:
                        z=par["intercept"]+sum((f["features"][u][n]-mu)/sd*c for n,mu,sd,c in zip(par["features"],par["mean"],par["scale"],par["coef"]))
                        pr=1/(1+exp(-z))
                        if a=="selective":assert isclose(pr,r["selective_scores"][u],abs_tol=5e-14)
                        if pr>=par["threshold"]:calc.add(u)
                    assert ids==calc
        for a in methods:
            s=res["arms"][a]["summary"];tp,fp,fn=np.array(pairs[a]).sum(0)
            assert [tp,fp,fn]==[s["tp"],s["fp"],s["fn"]]
            defined=[2*t/(2*t+b+c) for t,b,c in pairs[a] if 2*t+b+c];assert len(defined)==s["n_defined"] and isclose(s["macro_defined"],mean(defined))
        pooled={a:np.array(pairs[a]) for a in methods};grp={d:np.array([i for i,r in enumerate(pred) if key[r["id"]]["domain"]==d]) for d in sorted({r["domain"] for r in key.values()})};rng=np.random.default_rng(29030)
        draw=np.hstack([rng.choice(ii,(10000,len(ii))) for ii in grp.values()])
        def predmicro(a):
            cnt=pooled[a][draw].sum(1);tp,fp,fn=cnt.T;return 2*tp/(2*tp+fp+fn)
        s=predmicro("selective")
        for a in methods:
            if a=="selective":continue
            assert np.allclose(np.quantile(s-predmicro(a),[.025,.975]),res["selective_minus"][a]["micro"]["ci"],atol=2e-14)
        receipt[p]=dict(n=len(raw),opaque_reruns=len(raw),case_claim_count=card,last=rank,true_claims_by_reverse_reachable_index=last_age,methods=list(methods),restored_forecast_probabilities=True,bootstrap_trajectory_draws=len(draw),train_domains_disjoint=True)
    save(OUT/"independent-audit.json",receipt);print(receipt)
if __name__=="__main__":main()

