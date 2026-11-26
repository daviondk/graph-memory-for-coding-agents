"""Portable mixture-of-seeds and trajectory bootstrap on the four matched policies."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,gzip
import numpy as np
D=Path(__file__).resolve().parent
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def estimate(arr,group,metrics,seeds):
    n=len(seeds);cnt=np.bincount(group);ng=len(cnt);cluster=np.zeros((n,ng,len(metrics)))
    for i in range(n):np.add.at(cluster[i],group,arr[i])
    base=cluster.mean(0);r=np.random.default_rng(34091);rs=np.random.default_rng(34092);fixed=[];cross=[]
    for chunk in range(100):
        ix=r.integers(ng,size=(100,ng));mult=np.stack([np.bincount(v,minlength=ng) for v in ix]);den=(mult@cnt)[:,None]
        fixed.extend((mult@base)/den);ss=rs.integers(n,size=(100,n))
        for k,vec in enumerate(mult):cross.append(sum(vec@cluster[s] for s in ss[k])/(n*den[k]))
    a=np.quantile(fixed,[.025,.975],axis=0);b=np.quantile(cross,[.025,.975],axis=0)
    return {m:{"delta":float(arr[:,:,i].mean()),"conditional_ci":a[:,i].tolist(),"crossed_ci":b[:,i].tolist(),
               "per_seed":arr[:,:,i].mean(1).tolist()} for i,m in enumerate(metrics)}
def results():
    meta=get(D/"inputs.json");assert meta["plan"]==sha(D/"PROTOCOL_RU.md") and meta["program"]==sha(D/"measure.py")
    models=meta["models"];metrics=meta["metrics"];seeds=[13,17,29]
    rows=[]
    for s in seeds:
        p=D/f"four-arms-{s}.json.gz";assert meta["rows"][str(s)]==sha(p);rows.append(get(p))
    ids=sorted(rows[0]);assert len(ids)==2000 and all(set(x)==set(ids) for x in rows)
    t=[rows[0][q][0] for q in ids];assert all([x[q][0] for q in ids]==t for x in rows)
    names,group=np.unique(t,return_inverse=True);assert len(names)==1207
    arr=np.array([[x[q][1:] for q in ids] for x in rows]);assert arr.shape==(3,2000,4,6) and np.all((arr>=0)&(arr<=1))
    compare={}
    for i,j in [(0,2),(0,3),(1,2),(1,3),(0,1)]:
        z=estimate(arr[:,:,i,:]-arr[:,:,j,:],group,metrics,seeds)
        compare[models[i]+"/"+models[j]]=z
    return {"seeds":seeds,"n":len(ids),"trajectories":len(names),"models":models,"metrics":metrics,
       "means":{k:arr[:,:,j,:].mean((0,1)).tolist() for j,k in enumerate(models)},
       "seed_means":{str(s):{m:arr[k,:,j,:].mean(0).tolist() for j,m in enumerate(models)} for k,s in enumerate(seeds)},
       "comparisons":compare,"both_R35_primary_positive_lower_bounds_at_three_seeds":
            {key:all(compare[models[0]+"/"+m][metrics[0]][key][0]>0 for m in models[2:]) for key in ("conditional_ci","crossed_ci")},
       "input":sha(D/"inputs.json")}
def main():
    p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");a=p.parse_args();target=D/"results.json";r=results()
    if a.write and not target.exists():target.write_text(json.dumps(r,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8",newline="\n")
    assert get(target)==r
    print({k:[round(z["full_support_2048"]["delta"]*100,3),[round(v*100,3) for v in z["full_support_2048"]["conditional_ci"]],[round(v*100,3) for v in z["full_support_2048"]["crossed_ci"]]] for k,z in r["comparisons"].items()},flush=True)
if __name__=="__main__":main()
