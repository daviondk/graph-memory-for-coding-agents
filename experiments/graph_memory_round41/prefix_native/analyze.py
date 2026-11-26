import os
for key in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):
    os.environ[key]="1"
import numpy as np
from shared import D, SEEDS, read, sha, save


CONTRASTS = [
    ("wo_chunk_adjacency/firstfit", "graph_firstfit"),
    ("wo_chunk_adjacency/firstfit", "graph_dp"),
    ("full_rgcn/firstfit", "graph_firstfit"),
    ("full_rgcn/firstfit", "graph_dp"),
    ("wo_chunk_adjacency/strict", "graph_strict"),
    ("full_rgcn/strict", "graph_strict"),
    ("wo_chunk_adjacency/strict", "graph_firstfit"),
    ("full_rgcn/strict", "graph_firstfit"),
    ("wo_chunk_adjacency/strict", "graph_dp"),
    ("full_rgcn/strict", "graph_dp"),
    ("wo_chunk_adjacency/firstfit", "dense_firstfit"),
    ("wo_chunk_adjacency/firstfit", "full_rgcn/firstfit"),
    ("wo_chunk_adjacency/firstfit", "wo_chunk_adjacency/strict"),
    ("full_rgcn/firstfit", "full_rgcn/strict"),
    ("wo_chunk_adjacency/firstfit", "wo_chunk_adjacency/final_restricted_firstfit"),
    ("full_rgcn/firstfit", "full_rgcn/final_restricted_firstfit"),
    ("hybrid_dp", "wo_chunk_adjacency/firstfit"),
    ("hybrid_value", "wo_chunk_adjacency/firstfit"),
    ("hybrid_dp", "hybrid_value"),
    ("hybrid_dp", "graph_dp"),
    ("hybrid_dp", "graph_firstfit"),
    ("hybrid_value", "graph_dp"),
    ("hybrid_value", "graph_firstfit"),
]


def contrasts(values, clusters):
    n=max(clusters)+1
    sums=np.zeros((n,*values.shape[1:]))
    np.add.at(sums,clusters,values)
    totals=np.bincount(clusters)
    rng=np.random.default_rng(410141)
    boot=[]
    for _ in range(100):
        groups=rng.integers(0,n,size=(100,n))
        weights=np.stack([np.bincount(v,minlength=n) for v in groups])
        means=(weights@sums.reshape(n,-1)).reshape(100,*sums.shape[1:]) / (weights@totals)[:,None,None,None]
        seeds=rng.integers(len(SEEDS),size=(100,len(SEEDS)))
        boot.append(means[np.arange(100)[:,None],seeds].mean(axis=1))
    return np.quantile(np.concatenate(boot),[.025,.975],axis=0)


def main():
    assert sha(D/"outcomes.json.gz")==read(D/"scoring.json")["scores"]
    rows=read(D/"outcomes.json.gz")
    panels={"eligible":[r for r in rows if not r["pilot"] and r["eligible"]],
            "deferred":[r for r in rows if not r["pilot"]], "all":rows}
    tables={}
    for name, group in panels.items():
        ts,cids=np.unique([r["t"] for r in group],return_inverse=True)
        arms=sorted(group[0]["arms"]["13"])
        mat=np.array([[[r["arms"][str(s)][arm] for arm in arms] for s in SEEDS] for r in group])
        mu=mat.mean(axis=(0,1));seed_mu=mat.mean(axis=0)
        diffs=np.stack([mat[:,:,arms.index(a),:]-mat[:,:,arms.index(b),:] for a,b in CONTRASTS],axis=2)
        ci=contrasts(diffs,cids)
        tables[name]=dict(questions=len(group),trajectories=len(ts),
            means={arm:mu[i].tolist() for i,arm in enumerate(arms)},
            by_seed={str(seed):{arm:seed_mu[k,i].tolist() for i,arm in enumerate(arms)} for k,seed in enumerate(SEEDS)},
            paired=[dict(left=a,right=b,mean=diffs[:,:,i].mean(axis=(0,1)).tolist(),ci95=ci[:,i].tolist())
                    for i,(a,b) in enumerate(CONTRASTS)])
    assert tables["eligible"]["questions"]==901 and tables["eligible"]["trajectories"]==657
    save(D/"results.json",dict(panels=tables,measure_order=["Full Support","coverage","tokens"],
         replicates=10000,seed=410141,scoring=sha(D/"scoring.json"),implementation=sha(D/"analyze.py")))
    print("primary",tables["eligible"]["paired"][0])


if __name__=="__main__":
    main()
