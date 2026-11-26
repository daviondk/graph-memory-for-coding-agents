"""Summarize blocked wall clocks and storage with immutable inputs."""
import numpy as np
from bench import *
def analyze(save_results):
    reg=load("registration.json");seal=load("run-seal.json")
    assert seal==dict(registration=sha(D/"registration.json"),times=sha(D/"timings.json.gz"),exactness=sha(D/"exactness.json"))
    data=load("timings.json.gz");assert len(data)==105
    indexed={(r["rep"],r["m"],r["plan"]):r for r in data};assert len(indexed)==105
    draws=np.random.default_rng(SEED+2).integers(REPEAT,size=(10000,REPEAT))
    def comparison(x,y):
        a,b=np.array(x),np.array(y);vals=a[draws].mean(axis=1)/b[draws].mean(axis=1)
        return dict(ratio=float(a.mean()/b.mean()),ci95=np.quantile(vals,[.025,.975]).tolist(),faster=int((a<b).sum()))
    means={};ratios={};wm={};wr={}
    for m in (0,1,8):
        measures=("build_ns","write_ns","read_ns","checkpoint_ns","total_ns")
        by={p:[indexed[i,m,p] for i in range(REPEAT)] for p in PLANS}
        means[str(m)]={p:{k.replace("_ns","_ms"):float(np.mean([v[k] for v in rs])/1e6) for k in measures} for p,rs in by.items()}
        ratios[str(m)]={p+"_over_snapshot":comparison([r["total_ns"] for r in rs],[r["total_ns"] for r in by["snapshot"]]) for p,rs in by.items() if p!="snapshot"}
        if m==8:
            for k in map(str,KS):
                times={p:[r["warm_ns_per_read"][k] for r in rs] for p,rs in by.items()}
                wm[k]={p:float(np.mean(xs)/1000) for p,xs in times.items()}
                wr[k]={p+"_over_snapshot":comparison(xs,times["snapshot"]) for p,xs in times.items() if p!="snapshot"}
    exact=load("exactness.json")
    res=dict(ratio_convention="plan time divided by snapshot time; lower is faster",means_ms=means,paired=ratios,warm_mean_us=wm,warm_paired=wr,
        sizes={p:{k:v[k] for k in ("bytes","history_rows","history_btree_bytes","packet_payload_bytes") if k in v} for p,v in exact["plans"].items()},
        plans=reg["plans"],k=reg["k"],blocks=REPEAT,checks=exact["versions"]*len(KS)*len(PLANS),run_sha=sha(D/"run-seal.json"))
    if save_results:save("results.json",res)
    else:assert res==load("results.json")
    print(json.dumps(dict(primary=ratios["8"]["admitted_over_snapshot"],sizes=res["sizes"],times={m:{p:round(v["total_ms"],2) for p,v in r.items()} for m,r in means.items()},warm=wm)))
    return res
if __name__=="__main__":
    import sys
    analyze("--verify" not in sys.argv)
