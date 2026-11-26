"""Summarize matched query outcomes with whole-trajectory and seed resampling."""
import gzip,json,hashlib,os
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[k]="1"
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent
seeds=(13,17,29,37,41)
arms=("graph_dp","graph_firstfit","graph_strict","dense_firstfit")
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)

def crossed(values,clusters,indices):
    n=max(clusters)+1
    sums=np.zeros((n,*values.shape[1:]))
    np.add.at(sums,clusters,values)
    sizes=np.bincount(clusters)
    rng=np.random.default_rng(410141)
    result=[]
    for _ in range(100):
        named=rng.integers(0,n,size=(100,n))
        weight=np.stack([np.bincount(ix,minlength=n) for ix in named])
        means=(weight@sums.reshape(n,-1)).reshape((100,*sums.shape[1:]))/(weight@sizes)[:,None,None]
        shared=rng.integers(len(indices),size=(100,len(indices)))
        result.append(means[np.arange(100)[:,None],shared].mean(axis=1))
    return np.quantile(np.concatenate(result),[.025,.975],axis=0).tolist()

def run():
    seal=read(D/"scoring.json")
    rows=[]
    for i in range(8):
        p=D/f"outcomes-{i}.json.gz";assert hashlib.sha256(p.read_bytes()).hexdigest()==seal["scores"][str(i)]
        rows.extend(read(p))
    tables={}
    for cut in (25,50,75,100):
        for key,sub in [("eligible",[r for r in rows if not r["pilot"] and r["cut"]==cut and r["eligible"]]),
                        ("deferred_all",[r for r in rows if not r["pilot"] and r["cut"]==cut]),
                        ("all",[r for r in rows if r["cut"]==cut])]:
            labels,cids=np.unique([r["t"] for r in sub],return_inverse=True)
            x=np.array([[[r["arms"][str(s)][a] for a in arms] for s in seeds] for r in sub])
            means=x.mean(axis=(0,1));delta=x[:,:,0,:]-x[:,:,1,:]
            base=np.array([r["old"] for r in sub])
            prior=x[:,0,0,:]-base
            paired=delta.mean(axis=(0,1))
            z=dict(n=len(sub),trajectories=len(labels),means={a:means[i].tolist() for i,a in enumerate(arms)},
                seed13_R22=base.mean(axis=0).tolist(),seed13_R39=x[:,0,0,:].mean(axis=0).tolist(),
                prior_delta=prior.mean(axis=0).tolist(),primary_delta=paired.tolist(),by_seed=delta.mean(axis=0).tolist())
            if key=="eligible":
                z["primary_ci"]=crossed(delta,cids,seeds)
                z["seed13_prior_ci"]=crossed(prior[:,None,:],cids,(13,))
            tables[f"{cut}/{key}"]=z
    assert tables["50/eligible"]["n"]==901 and tables["50/eligible"]["trajectories"]==657
    stats=dict(groups=tables,seeds=seeds,scorer=seal["official_unique_lists"],bootstrap=10000)
    (D/"results.json").write_text(json.dumps(stats,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(tables["50/eligible"])

if __name__=="__main__":run()

