"""Paired crossed trajectory/seed resampling with simultaneous budget-curve bands."""
import os
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
import json,gzip,hashlib
from collections import defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent;WORK=HERE.parents[1];RR=HERE.parent/"strong_reader_controls"
SEEDS=(13,17,29,37,41);BS=(256,512,1024,2048,4096,8192)
def read(p):
    z=p.read_bytes();return json.loads(gzip.decompress(z) if p.suffix==".gz" else z)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    z=(json.dumps(v,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(z,mtime=0) if p.suffix==".gz" else z)
def run():
    parent=WORK/"graph_memory_round32/isetrace_five_seeds/per-query.json.gz";orig=read(parent);idx=orig["metrics"].index("full_support_2048")
    pre={(seed,q):(t,dense[idx],graph[idx]) for seed,q,t,dense,graph in orig["rows"]}
    groups=defaultdict(list);files=[RR/f"auc-outcomes-{i}.json.gz" for i in range(8)]
    names=["cost-dense.FS2048","role-global.FS2048","cost-role.FS2048","cost-global.FS2048","cost-role.C_AUC","cost-role.FS_AUC",*[f"cost-role.C{k}" for k in BS],*[f"cost-role.FS{k}" for k in BS]]
    for p in files:
        for q,r in read(p).items():
            m=[]
            for seed in SEEDS:
                t,de,gl=pre[seed,q];assert t==r["t"]
                a=r["seeds"][str(seed)];cost,role=np.asarray(a["cost"]),np.asarray(a["frozen"]);d=cost-role
                m.append([cost[11]-de,role[11]-gl,d[11],cost[11]-gl,*d[:2],*d[2:8],*d[8:14]])
            groups[t].append(np.array(m))
    assert len(groups)==1207 and sum(map(len,groups.values()))==2000
    accum=np.array([np.sum(g,axis=0) for g in groups.values()]);n=np.array(list(map(len,groups.values())))
    obs=100*accum.sum(axis=0).mean(axis=0)/n.sum()
    assert np.allclose(obs[:4],[7.49,1.16,.86,2.02])
    rng=np.random.default_rng(45121);fixed=[];cross=[]
    for _ in range(400):
        ix=rng.integers(len(n),size=(50,len(n)));sx=rng.integers(5,size=(50,5))
        den=n[ix].sum(axis=1)
        vals=100*accum[ix].sum(axis=1)/den[:,None,None]
        fixed.extend(vals.mean(axis=1));cross.extend(vals[np.arange(50)[:,None],sx,:].mean(axis=1))
    fixed,cross=np.asarray(fixed),np.asarray(cross)
    cis=lambda x:np.quantile(x,[.025,.975],axis=0).T
    delseed=100*(accum.sum(axis=(0,1))-accum.sum(axis=0))/(4*n.sum())
    deltraj=100*((accum.sum(axis=0)-accum).mean(axis=1))/(n.sum()-n[:,None])
    tables={k:{"pp":obs[j],"fixed_ci95":cis(fixed)[j].tolist(),"crossed_ci95":cis(cross)[j].tolist(),"drop_one_seed":[delseed[:,j].min(),delseed[:,j].max()],"drop_one_trajectory":[deltraj[:,j].min(),deltraj[:,j].max()]} for j,k in enumerate(names)}
    for sl in (slice(6,12),slice(12,18)):
        std=cross[:,sl].std(axis=0,ddof=1);assert np.all(std>0)
        critical=np.quantile(np.abs((cross[:,sl]-obs[sl])/std).max(axis=1),.95)
        for name,v,s in zip(names[sl],obs[sl],std):tables[name]["crossed_simultaneous_ci95"]=[v-critical*s,v+critical*s]
    blocks={k:{"n":len(g),"sums":np.sum(g,axis=0).tolist()} for k,g in groups.items()}
    save(HERE/"clusters.json.gz",blocks)
    save(HERE/"results.json",{"n":int(n.sum()),"n_trajectories":len(n),"seeds":SEEDS,"draws":len(cross),"contrast_order":names,"contrasts":tables,"inputs":{p.relative_to(WORK).as_posix():sha(p) for p in [parent,*files]},"protocol":sha(HERE/"PROTOCOL_RU.md"),"clusters":sha(HERE/"clusters.json.gz")})
if __name__=="__main__":run()
