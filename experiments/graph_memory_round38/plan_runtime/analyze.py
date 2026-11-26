"""Report steady and startup-amortized complete lifecycles with paired cluster intervals."""
from inputs import *
import numpy as np
def effect(a,b,ids):
    ids=np.array(ids);labs=sorted(set(ids));u=np.array([a[ids==k].sum() for k in labs]);v=np.array([b[ids==k].sum() for k in labs])
    rng=np.random.default_rng(380451);ix=rng.integers(len(labs),size=(10000,len(labs)))
    return dict(ratio=float(u.sum()/v.sum()),ci95=np.quantile(u[ix].sum(1)/v[ix].sum(1),[.025,.975]).tolist())
def summarize(raw,seal):
    p=get(D/"plan.json")["panel"];sch=get(D/"schedule.json.gz");selected=get(H/"decisions.json.gz")
    rep=[sch[q]["repo"] for q in p];iss=[sch[q]["issue"] for q in p]
    res={}
    for s,rows in raw.items():
        a=np.array([[[blk[m] for m in "ALH"] for blk in rows[q]] for q in p])
        assert a.shape==(128,6,3,13)
        avg=a.mean(1);assert np.array_equal(a[:,:,:,6:],np.repeat(a[:,0:1,:,6:],6,axis=1))
        costs={}
        boot=np.mean(seal["compile_all"][s],axis=0)/len(p)
        for unit,off in (("ns",0),("cycles",3)):
            values={}
            components={"ingest":avg[:,:,off],"edit":avg[:,:,off+1],"read":avg[:,:,off+2],"post_ingest":avg[:,:,off+1:off+3].sum(2),"lifecycle":avg[:,:,off:off+3].sum(2)}
            amm=components["lifecycle"].copy();amm[:,2]+=boot[0 if off==0 else 1];components["startup_amortized_lifecycle"]=amm
            for label,x in components.items():
                d={"mean":{m:float(x[:,i].mean()) for i,m in enumerate("ALH")}}
                if label in ("lifecycle","post_ingest","startup_amortized_lifecycle"):
                    b=np.array([x[i,"AL".index(selected[q]["H"])] for i,q in enumerate(p)])
                    d["bare_selected_mean"]=float(b.mean())
                    d["steady_oracle_mean"]=float(np.minimum(x[:,0],x[:,1]).mean())
                    for name,v in (("H/A",x[:,0]),("H/L",x[:,1]),("H/bare",b)):
                        d[name]=dict(repo=effect(x[:,2],v,rep),issue=effect(x[:,2],v,iss))
                    d["per_repo"]={r:dict(n=sum(z==r for z in rep),mean={m:float(x[np.array(rep)==r,j].mean()) for j,m in enumerate("ALH")}) for r in sorted(set(rep))}
                values[label]=d
            costs[unit]=values
        counts={m:dict(zip(seal.get("columns",get(D/"run-seal.json")["columns"])[6:],avg[:,i,6:].sum(0).astype(int).tolist())) for i,m in enumerate("ALH")}
        res[s]=dict(costs=costs,sql=counts,startup_amortized_ns=float(boot[0]),startup_amortized_cycles=float(boot[1]))
    return res
def main():
    stages={}
    for name,log,se in (("initial","raw.json.gz","run-seal.json"),("packed","packed-raw.json.gz","packed-run-seal.json")):
        seal=get(D/se);assert sha(D/log)==seal["raw"]
        stages[name]=summarize(get(D/log),seal)
    put(D/"results.json",stages)
    for name,ss in stages.items():
        for s,v in ss.items():
            print(name,s)
            for metric in ("ingest","post_ingest","lifecycle","startup_amortized_lifecycle"):
                row=v["costs"]["ns"][metric]
                print(metric,[round(x/1000,2) for x in row["mean"].values()],row.get("H/L",{}).get("repo",{}))
if __name__=="__main__":main()
