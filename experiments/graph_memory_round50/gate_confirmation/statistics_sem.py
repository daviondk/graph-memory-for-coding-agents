from paths_a import ARMS
import numpy as np

PAIRS=(("adaptive","dense"),("linked_dense","dense"))

def analyze(rows):
    names=list(ARMS);vals=np.array([[r["arms"][s][:5] for s in names] for r in rows]);n=len(vals)
    assert len({r["cluster"] for r in rows})==n
    diffs=np.stack([vals[:,names.index(a)]-vals[:,names.index(b)] for a,b in PAIRS],axis=1)
    flat=diffs.reshape(n,-1);rng=np.random.default_rng(470091);samples=[]
    for _ in range(100):
        draw=rng.integers(n,size=(100,n))
        weights=np.stack([np.bincount(k,minlength=n) for k in draw])
        samples.append(weights@flat/n)
    ci=100*np.quantile(np.concatenate(samples).reshape(-1,*diffs.shape[1:]),[.025,.975],axis=0)
    contrasts={}
    for j,(a,b) in enumerate(PAIRS):
        d=diffs[:,j]
        contrasts[a+"-"+b]=dict(pp=(100*d.mean(0)).tolist(),cluster_ci=ci[:,j].T.tolist(),
                     wins=(d>1e-12).sum(0).tolist(),losses=(d< -1e-12).sum(0).tolist())
    return dict(n=n,means={a:vals[:,j].mean(0).tolist() for j,a in enumerate(names)},contrasts=contrasts)
