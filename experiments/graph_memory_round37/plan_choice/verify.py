"""Held-out checks, independent scikit-learn refits and independent timing arithmetic."""
from features import D,P,get,sha,put
from sklearn.linear_model import LogisticRegression,Ridge
from sklearn.preprocessing import StandardScaler
from sklearn import __version__ as sklearn_version
import numpy as np,math

def run():
    seal=get(D/"fit-seal.json");fs=get(D/"features-seal.json");ls=get(D/"live-seal.json")
    for file,key in (("decisions.json.gz","decisions"),("models.json","model"),("folds.json.gz","folds"),("demand-predictions.json.gz","demand")):
        assert sha(D/file)==seal[key]
    assert seal["fit_code"]==sha(D/"model.py") and ls["code"]==sha(D/"live.py") and fs["code"]==sha(D/"features.py")
    assert sha(D/"PROTOCOL_RU.md")==seal["protocol"]==fs["protocol"] and ls["samples"]==sha(D/"live-timings.json.gz")
    f=get(D/"features.json.gz");folds=get(D/"folds.json.gz");dec=get(D/"decisions.json.gz");prob=get(D/"demand-predictions.json.gz")
    outcome={z["q"]:z for z in get(P/"followup.json.gz")};old=get(P/"physical.json.gz")["observed"];new=get(D/"live-timings.json.gz")
    scores=[];ps=[];tot=0
    for repo,fold in folds.items():
        tra=fold["cost_train"];te=fold["cost_test"];broad=fold["demand_train"];bt=fold["demand_test"]
        assert all(outcome[q]["repo"]==repo for q in te+bt) and all(outcome[q]["repo"]!=repo for q in tra+broad)
        assert set(outcome[q]["issue"] for q in tra+broad).isdisjoint(outcome[q]["issue"] for q in te+bt)
        X=np.array([f[q] for q in tra]);sc=StandardScaler().fit(X)
        v={m:np.array([np.mean([rep[m][0]+rep[m][1] for rep in old[q]]) for q in tra]) for m in "AL"}
        total=v["A"]+v["L"];ridge=Ridge(alpha=.1*len(tra),solver="svd").fit(sc.transform(X),(v["A"]-v["L"])/total,sample_weight=total/total.mean())
        pred=ridge.predict(sc.transform([f[q] for q in te]))
        assert [dec[q]["H"] for q in te]==["L" if z>0 else "A" for z in pred]
        assert [dec[q]["const"] for q in te]==["L" if v["L"].sum()<v["A"].sum() else "A"]*len(te)
        scores.extend(abs(pred-np.array([dec[q]["score"] for q in te])))
        X=np.array([f[q] for q in broad]);sc=StandardScaler().fit(X)
        yy=np.array([outcome[q]["strict"]["reads"]==0 for q in broad])
        logit=LogisticRegression(C=1/(.2*len(broad)),tol=1e-11,max_iter=1000,solver="lbfgs")
        logit.fit(sc.transform(X),yy)
        pp=logit.predict_proba(sc.transform([f[q] for q in bt]))[:,1]
        ps.extend(np.abs(pp-np.array([prob[q][0] for q in bt])))
        tot+=len(te)
    assert tot==len(new)==128 and max(scores)<1e-9 and max(ps)<5e-6
    result=get(D/"results.json")
    for mode,raw in (("offline",old),("live",new)):
        vals=[]
        for q in dec:
            m=dec[q]["H"] if mode=="offline" else "H"
            vals.append(np.mean([rep[m][0]+rep[m][1] for rep in raw[q]]))
        assert np.isclose(np.mean(vals),result[mode]["means_ns"]["H"])
    diag=dict(models=5,held_out_decisions=tot,zero_predictions=len(ps),max_abs_ridge=float(max(scores)),max_abs_logistic=float(max(ps)),sklearn=sklearn_version)
    put(D/"refit-audit.json",diag);print(diag)
if __name__=="__main__":run()
