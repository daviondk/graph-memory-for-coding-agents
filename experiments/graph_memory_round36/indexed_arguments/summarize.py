"""Trajectory-paired descriptive intervals for prespecified comparisons on total runtime."""
from experiment import D,load,put,sha,np,Counter,methods
def effect(n,d):
    n=np.asarray(n,float);d=np.asarray(d,float);rng=np.random.default_rng(360614)
    ratios=[]
    for _ in range(100):
        idx=rng.integers(len(n),size=(100,len(n)))
        ratios.extend(n[idx].sum(1)/d[idx].sum(1))
    return dict(ratio=float(n.sum()/d.sum()),ci95=np.quantile(ratios,[.025,.975]).tolist())
def summarize():
    t=load(D/"timing-seal.json");assert sha(D/"clock_samples.json.gz")==t["data"]
    plan=load(D/"plan.json");r=load(D/"clock_samples.json.gz");assert set(r)==set(plan["panel"])
    clocks=("cycles","cpu_ns","wall_ns")
    X=np.array([[[rep[m] for m in methods] for rep in r[t]["samples"]] for t in plan["panel"]])
    assert X.shape==(96,6,3,3)
    avg=X.mean(1)
    output={"timing":{}, "absolute":{}}
    for i,k in enumerate(clocks):
        output["timing"][k]={label:effect(avg[:,a,i],avg[:,b,i]) for label,a,b in (("C/A",2,0),("B/A",1,0),("C/B",2,1))}
        output["absolute"][k]={m:dict(summed=float(avg[:,j,i].sum()),zero_trials=int(np.sum(X[:,:,j,i]==0)),
           median=float(np.median(avg[:,j,i])),mean=float(avg[:,j,i].mean()),
           faster_vs_A=int(np.sum(avg[:,j,i]<avg[:,0,i])),equal_vs_A=int(np.sum(avg[:,j,i]==avg[:,0,i]))) for j,m in enumerate(methods)}
    c=load(D/"count-seal.json");assert c["plan"]==t["plan"]==sha(D/"plan.json")
    histories={};s=Counter()
    for f,h in c["files"].items():
        assert sha(D/f)==h;sh=load(D/f);assert not set(sh)&set(histories);histories.update(sh)
    for h in histories.values():s.update(h["counts"])
    assert len(histories)==1207 and sum(v["cuts"] for v in histories.values())==4828 and s["events"]==72186
    output["counts"]=dict(s)
    output["decoded_hit_trajectories"]=sum(v["counts"].get("decoded_only_hits",0)>0 for v in histories.values())
    output["C_nonempty_histories"]=sum(v["counts"].get("C_nonempty_calls",0)>0 for v in histories.values())
    put(D/"results.json",output)
    print(output["timing"],flush=True)
    print(dict(s),flush=True)
if __name__=="__main__":summarize()
