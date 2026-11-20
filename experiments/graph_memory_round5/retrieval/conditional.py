import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','BLIS_NUM_THREADS'):os.environ[k]='1'
import numpy as np
from scipy.optimize import minimize
from common5 import sha
def fit(x,sizes,gold,penalty):
    # Conditional log loss, one normalized term per request. A query has exactly one relevant item.
    x=np.ascontiguousarray(x,dtype=np.float64);sizes=np.asarray(sizes);start=np.r_[0,np.cumsum(sizes)[:-1]]
    group=np.repeat(np.arange(len(start)),sizes);yi=start+np.asarray(gold)
    scale=np.sqrt(np.mean(np.add.reduceat(x*x,start,axis=0)/sizes[:,None],axis=0))
    scale=np.maximum(scale,.15);x/=scale;target=x[yi].mean(axis=0)
    def objective(w):
        z=x@w;peak=np.maximum.reduceat(z,start);tmp=np.exp(z-peak[group]);total=np.add.reduceat(tmp,start)
        loss=(np.log(total)+peak-z[yi]).mean()+penalty*(w@w)/2
        grad=(x.T@(tmp/total[group]))/len(start)-target+penalty*w
        return loss,grad
    sol=minimize(objective,np.zeros(x.shape[1]),method='L-BFGS-B',jac=True,options={'maxiter':500,'ftol':1e-9,'gtol':2e-6})
    if not sol.success:raise ValueError(sol.message)
    return dict(weights=(sol.x/scale).tolist(),nit=sol.nit,objective=sol.fun,l2=penalty,max_grad=float(abs(sol.jac).max()))
def positions(orders):
    return np.column_stack([np.argsort(o,kind='stable')+1 for o in orders]).astype(float)
def basis(r):
    # Rank magnitudes and bins are independent of the original ordering of declarations.
    n=len(r);return np.concatenate([1/r,(n-r)/max(n-1,1),np.exp(-(r-1)/2),np.log1p(r)/np.log1p(n),*[r<=k for k in (1,2,3,5,10)],*[(r/n)<=t for t in (.125,.25,.5,.75)]],axis=1)
def shuffled(extra,case):
    n=len(extra);shift=1+int(sha("rankplacebo|"+case)[:12],16)%max(1,n-1)
    return np.roll(extra,shift,axis=0)
def ordered(scores):
    return np.argsort(-np.asarray(scores),kind='stable').astype(int).tolist()

