"""Paired, two-way bootstrap over balanced question blocks and randomized timing rounds."""
import numpy as np
from source import ROOT,blocks,read,write

ORDER=("scan","cover","partial","eligible","journal")
def main():
    data=read("workload.json.gz")
    bs=blocks(data)
    selected=[data[i] for group in bs for i in group]
    cuts=sum(e["cuts"] for e in selected)
    edge_count=sum(c[4] is not None for e in selected for c in e["candidates"])
    rows=read("timings.json.gz")+read("frontier-timings.json.gz")
    assert len(rows)==124
    rng=np.random.default_rng(528830)
    r=rng.integers(4,size=(10000,4))
    b=rng.integers(len(bs),size=(10000,len(bs)))
    stats={}
    for mode in sorted({x["reads"] for x in rows}):
        plans={};samples={}
        for plan in ORDER:
            trials=sorted((x for x in rows if (x["plan"],x["reads"])==(plan,mode)),key=lambda v:v["rep"])
            if not trials:continue
            assert [x["rep"] for x in trials]==[0,1,2,3]
            block=np.array([[x["blocks"][str(i)] for i in range(len(bs))] for x in trials])
            runtime=block[:,:,0]
            build=np.array([x["build_ns"] for x in trials]);end=np.array([x["checkpoint_ns"] for x in trials])
            warm=runtime.sum(axis=1)
            total=warm+build+end
            plans[plan]=dict(total_ms=total.mean()/1e6,warm_ms=warm.mean()/1e6,setup_ms=build.mean()/1e6,checkpoint_ms=end.mean()/1e6,
                             write_us=block[:,:,1].sum(axis=1).mean()/cuts/1000,
                             read_us=block[:,:,2].sum(axis=1).mean()/(cuts*mode)/1000 if mode else None,
                             db_bytes=trials[0]["db_bytes"],history_rows=trials[0]["history_rows"],
                             rep_total_ms=(total/1e6).tolist())
            # Same question blocks and machine repeats in both arms. Phase overheads repeat once per run.
            samples[plan]=(runtime[r[:,:,None],b[:,None,:]].sum(axis=2)+build[r]+end[r]).mean(axis=1)
        contrasts={}
        for baseline in (x for x in ORDER if x in plans and x!="journal"):
            a=plans[baseline];j=plans["journal"]
            ratio=a["total_ms"]/j["total_ms"]
            ratio_boot=samples[baseline]/samples["journal"]
            contrasts[baseline]=dict(speedup=ratio,ci=[float(i) for i in np.quantile(ratio_boot,[.025,.975])],
                                     saved_pct=100*(1-1/ratio),paired_wins=sum(x>y for x,y in zip(a["rep_total_ms"],j["rep_total_ms"])))
        stats[mode]=dict(plans=plans,contrasts=contrasts)
    write("results.json",dict(seeds=dict(bootstrap=528830),n_episodes=len(selected),blocks=len(bs),reveals=cuts,
         observed_edges=edge_count,all=read("correctness.json")["journal"],modes=stats))
    for mode,z in stats.items():
        print(mode,' '.join(f"{p}={v['total_ms']:.1f}" for p,v in z['plans'].items()),'CI vs partial',z['contrasts']['partial'])
if __name__=="__main__":
    main()
