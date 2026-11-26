"""Post-hoc sensitivity to multiplicity, using the four transfer seeds only."""
import json,gzip
from pathlib import Path
from collections import defaultdict
import numpy as np
S=Path(__file__).resolve().parent
data=json.loads(gzip.decompress((S/"outcomes.json.gz").read_bytes()))
keys=["full_support","coverage","recall5","mrr"];seeds=["17","29","37","41"]
groups=defaultdict(list)
for q in sorted(data["17"]["factor"]):
    d=[]
    for seed in seeds:
        arms=data[seed];ref=arms["global_0.03"][q];t=ref[0]
        dif=[np.array(ref[1:])-np.array(arms[c][q][1:]) for c in ("factor","alpha_0.75")]
        d.append(np.stack(dif))
    groups[t].append(np.mean(d,axis=0))
sums=np.array([np.sum(groups[t],axis=0) for t in sorted(groups)]);n=np.array([len(groups[t]) for t in sorted(groups)])
rng=np.random.default_rng(13);dist=[]
for _ in range(40):
    ix=rng.integers(len(n),size=(250,len(n)));dist.append(sums[ix].sum(axis=1)/n[ix].sum(axis=1)[:,None,None])
bs=np.concatenate(dist);out={}
for m in [1,4,8]:
    ci=np.quantile(bs,[.025/m,1-.025/m],axis=0)
    out[str(m)]={c:{k:ci[:,a,j].tolist() for j,k in enumerate(keys)} for a,c in enumerate(("factor","alpha_0.75"))}
print(json.dumps({"comparisons":out,"n":2000,"trajectory_resamples":10000,"seed":13,"scope":"descriptive Bonferroni percentile intervals; m=4 outcomes versus factor; m=8 outcomes times two controls"},sort_keys=True,indent=2))