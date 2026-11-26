"""Five disjoint repository folds; all feature scalers and both learners fitted on training repositories."""
from features import *
import numpy as np
from scipy.special import expit
from scipy.optimize import minimize
from math import exp
L2=.1

def design(X):
    mu=X.mean(0);scale=X.std(0);scale[scale<1e-12]=1
    return np.column_stack((np.ones(len(X)),(X-mu)/scale)),mu,scale
def pack(beta,mu,scale):
    # Equivalent raw-feature affine model for fast deployment, fitted intercept unpenalized.
    coef=beta[1:]/scale;intercept=beta[0]-np.dot(coef,mu)
    return dict(intercept=float(intercept),coef=coef.tolist(),train_mean=mu.tolist(),train_scale=scale.tolist())
def apply(m,x):return m["intercept"]+sum(a*b for a,b in zip(m["coef"],x))
def probability(m,x):
    raw=max(-700,min(700,apply(m,x)))
    return 1/(1+exp(-raw))

def ridge(X,a,l):
    z,mu,sc=design(X);y=(a-l)/(a+l);w=(a+l)/np.mean(a+l)
    reg=np.eye(z.shape[1])*L2;reg[0,0]=0
    beta=np.linalg.solve((z.T*w)@z/len(z)+reg,z.T@(w*y)/len(z))
    return pack(beta,mu,sc)
def logistic(X,y):
    z,mu,sc=design(X)
    def loss(b):
        v=z@b
        return np.mean(np.logaddexp(0,v)-y*v)+L2*np.dot(b[1:],b[1:]),z.T@(expit(v)-y)/len(y)+2*L2*np.r_[0,b[1:]]
    res=minimize(loss,np.zeros(z.shape[1]),jac=True,method="L-BFGS-B",options={"ftol":1e-14,"gtol":1e-9,"maxiter":150})
    assert res.success
    return pack(res.x,mu,sc)
def train():
    current=get(D/"features.json.gz");fu={r["q"]:r for r in get(P/"followup.json.gz")};panel=get(P/"physical-plan.json")["panel"]
    full=sorted(q for q,r in fu.items() if r["prefix"]=="clean" and r["strict"]["stop"] in ("mutation","finished"))
    assert len(full)==756 and len(panel)==128 and set(panel)<=set(full)
    raw=get(P/"physical.json.gz")["observed"]
    repos=sorted({fu[q]["repo"] for q in panel});assert len(repos)==5
    models={};selection={};probs={};groups={}
    for testrepo in repos:
        tra=[q for q in panel if fu[q]["repo"]!=testrepo];test=[q for q in panel if fu[q]["repo"]==testrepo]
        broad=[q for q in full if fu[q]["repo"]!=testrepo];btest=[q for q in full if fu[q]["repo"]==testrepo]
        assert not {fu[q]["issue"] for q in tra+broad}&{fu[q]["issue"] for q in test+btest}
        assert not set(tra)&set(test) and not set(broad)&set(btest)
        # Only training costs are accessed in this fold.
        a,l=[np.array([np.mean([r[m][0]+r[m][1] for r in raw[q]]) for q in tra]) for m in "AL"]
        fit=ridge(np.array([current[q] for q in tra]),a,l)
        ztrain=np.array([fu[q]["strict"]["reads"]==0 for q in tra])
        byzero=[float((a-l)[ztrain==z].mean()) for z in (False,True)]
        known=np.array([float(fu[q]["strict"]["reads"]==0) for q in broad])
        demand=logistic(np.array([current[q] for q in broad]),known)
        const="L" if l.sum()<a.sum() else "A";pr=float(known.mean())
        models[testrepo]=dict(ridge=fit,logistic=demand,constant=const,train_zero_probability=pr,train_deltas_conditional=byzero)
        groups[testrepo]=dict(cost_train=sorted(tra),cost_test=sorted(test),demand_train=broad,demand_test=btest)
        for q in btest:probs[q]=[probability(demand,current[q]),pr]
        for q in test:
            pred=apply(fit,current[q]);zero=probs[q][0];gate=zero*byzero[1]+(1-zero)*byzero[0]
            selection[q]=dict(H="L" if pred>0 else "A",J="L" if gate>0 else "A",const=const,p=zero,score=pred)
    assert set(selection)==set(panel) and set(probs)==set(full)
    put(D/"fit-seal.json",dict(model=put(D/"models.json",models),decisions=put(D/"decisions.json.gz",selection),folds=put(D/"folds.json.gz",groups),
       demand=put(D/"demand-predictions.json.gz",probs),parent_features=sha(D/"features-seal.json"),fit_code=sha(Path(__file__)),protocol=sha(D/"PROTOCOL_RU.md"),L2=L2))
    print("Sealed crossfit selectors",len(selection),len(probs),len(models))
if __name__=="__main__":train()
