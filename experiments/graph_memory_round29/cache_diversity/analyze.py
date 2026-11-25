"""Compare equal-K oracle and certifiable hits, with paired intervals by article."""
import numpy as np
from diverse import D,ROOT,POLICIES,read,save,sha

def main():
    source=read(D/"result-seal.json");rows=read(D/"rows.json.gz")
    assert source["rows"]==sha(D/"rows.json.gz")
    sc=read(ROOT/"multi_retraction/scenarios.json.gz");fields=source["fields"];aggregate={};effects={}
    for group in ("all","independent","targeted"):
        ids=[(q,c) for q,cond in rows.items() for c in cond if group=="all" or c.startswith(group+"-")]
        titles=sorted({sc[q]["article"] for q,c in ids});cl=[[i for i,(q,c) in enumerate(ids) if sc[q]["article"]==t] for t in titles]
        rng=np.random.default_rng(291237);draws=rng.integers(len(titles),size=(10000,len(titles)))
        aggregate[group]={};effects[group]={}
        val={a:np.asarray([rows[q][c][a] for q,c in ids]) for a in rows[ids[0][0]][ids[0][1]]}
        for name,A in val.items():aggregate[group][name]={"n":len(A),**dict(zip(fields,A.sum(axis=0).astype(int).tolist()))}
        for k in (8,64):
            lead=val["pareto"+str(k)]
            for mode in POLICIES[:-1]:
                other=val[mode+str(k)];diff=lead[:,:2]-other[:,:2]
                avg=np.asarray([diff[ix].mean(axis=0) for ix in cl])
                v=100*avg[draws].mean(axis=1)
                effects[group][f"pareto{k}_vs_{mode}{k}"]={"oracle_and_certified_pp":(100*diff.mean(axis=0)).tolist(),
                    "ci":np.percentile(v,[2.5,97.5],axis=0).T.tolist(),"oracle_wins":int((diff[:,0]>0).sum()),"oracle_losses":int((diff[:,0]<0).sum())}
    save(D/"results.json",{"strict":source["strict"],"main_cases":576,"counts":aggregate,"effects":effects})
    print(aggregate["all"]);print({k:v for k,v in effects["all"].items() if "64_" in k})
if __name__=="__main__":main()
