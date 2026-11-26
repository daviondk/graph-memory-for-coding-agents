"""Issue-clustered identification bounds and paired timing contrasts."""
from native import D,S,get,save,sha
from collections import defaultdict,Counter
import numpy as np
CLOSED={"mutation","finished"}
def pooled(arr,den,ids):
    a=np.asarray(arr,float);b=np.asarray(den,float);ids=np.asarray(ids);names=sorted(set(ids))
    ag=np.array([a[ids==i].sum() for i in names]);bg=np.array([b[ids==i].sum() for i in names]);assert bg.sum()>0
    rng=np.random.default_rng(371802); ix=rng.integers(len(names),size=(10000,len(names)))
    sums=bg[ix].sum(1);valid=sums!=0;boot=ag[ix].sum(1)[valid]/sums[valid]
    return dict(ratio=float(ag.sum()/bg.sum()),ci95=np.quantile(boot,[.025,.975]).tolist(),clusters=len(names),eligible_replicates=int(valid.sum()))
def zone(rows):
    if not rows:return {}
    z=[r["strict"] for r in rows];ids=[r["issue"] for r in rows];N=len(rows)
    closed=np.array([t["stop"] in CLOSED for t in z]);pos=np.array([t["reads"]>0 for t in z]);zeros=~pos
    tagged=Counter((t["stop"],bool(t["reads"])) for t in z)
    loose=[r["ignore_opaque"] for r in rows]
    rate=lambda fields: pooled(fields,np.ones(N),ids)
    return dict(N=N,runs=len({r["rid"] for r in rows}),issues=len(set(ids)),closed=int(closed.sum()),positive=int(pos.sum()),
       censored_positive=int((~closed&pos).sum()),certified_zero=int((closed&zeros).sum()),unknown_zero=int((~closed&zeros).sum()),
       bounds_known_zero=[rate((closed&zeros).astype(int)),rate(zeros.astype(int))],
       closed_zero_rate=pooled((closed&zeros).astype(int),closed.astype(int),ids) if closed.any() else None,
       closed_hist=dict(Counter(t["reads"] for t in z if t["stop"] in CLOSED)),prefix_hist=dict(Counter(t["reads"] for t in z)),
       stops={s:dict(zero=tagged[s,False],positive=tagged[s,True]) for s in sorted({t["stop"] for t in z})},
       recorded_reads=sum(t["reads"] for t in z),all_views=sum(t["any_view"] for t in z),numbered=sum(t["numbered_view"] for t in z),
       certified_zero_but_unnumbered_or_uninformative_view=sum(t["any_view"]>0 and t["reads"]==0 and t["stop"] in CLOSED for t in z),
       censored_zero_but_later_view=sum(t["stop"] not in CLOSED and t["reads"]==0 and h["reads"]>0 for t,h in zip(z,loose)),
       ignoring_opaque_closed_zero=sum(t["stop"] in CLOSED and t["reads"]==0 for t in loose),ignoring_opaque_stops=dict(Counter(t["stop"] for t in loose)),
       previous_study=sum(r["old"] is not None for r in rows),
       previous_strict_positive=sum(r["old"] is not None and r["strict"]["reads"]>0 for r in rows))
def analyze():
    raw=get(D/"followup.json.gz");byq={r["q"]:r for r in raw};new=get(D/"physical.json.gz");panel=get(D/"physical-plan.json")["panel"]
    zones={c+"_"+f:zone([r for r in raw if (r["cohort"],r["prefix"])==(c,f)]) for c in ("main","secondary") for f in ("clean","opaque")}
    base=np.array([byq[q]["strict"]["reads"] for q in panel]);ids=np.array([byq[q]["issue"] for q in panel])
    phys={};work={}
    for mode in ("observed","uniform"):
        X=np.array([[[t[m] for m in "AML"] for t in new[mode][q]] for q in panel]);assert X.shape==(128,6,3,8)
        Y=X.mean(axis=1);assert np.all(Y[:,:,7]==(base[:,None] if mode=="observed" else 1))
        phys[mode]={}
        work[mode]={m:dict(writes=int(Y[:,j,4].sum()),pre_rows=int(Y[:,j,5].sum()),lookup_rows=int(Y[:,j,6].sum()),lookups=int(Y[:,j,7].sum()))
                    for j,m in enumerate("AML")}
        for k,mask in (("all",np.ones(128,dtype=bool)),("zero",base==0),("positive",base>0)):
            t=Y[mask];v={}
            for unit,columns in (("wall_ns",(0,1)),("cycles",(2,3))):
                total=t[:,:,columns[0]]+t[:,:,columns[1]]
                v[unit]=dict(means={m:float(total[:,j].mean()) for j,m in enumerate("AML")},
                    vs_A=pooled(total[:,2],total[:,0],ids[mask]),vs_M=pooled(total[:,2],total[:,1],ids[mask]))
            v["n"]=int(mask.sum());phys[mode][k]=v
    # Secondary reconstruction using stored one-read/four-read timings only on actual matched prior cases.
    old_meas=get(S/"timings.json.gz");rmap={r["old"]:r for r in raw if r["old"]};assert set(old_meas)<=set(rmap)
    keep=[q for q in old_meas if rmap[q]["prefix"]=="clean" and rmap[q]["strict"]["stop"] in CLOSED]
    bridge={}
    for q in keep:
        rate=rmap[q]["strict"]["reads"];assert rate>=1
        bridge[q]={m:float(np.mean([a[m][0]+a[m][1]+(rate-1)*a[m][2]/3 for a in old_meas[q]])) for m in "AML"}
    matched=dict(n=len(keep),issues=len({rmap[q]["issue"] for q in keep}),read_hist=dict(Counter(rmap[q]["strict"]["reads"] for q in keep)),
        mean_modeled_ns={m:float(np.mean([v[m] for v in bridge.values()])) for m in "AML"} if keep else {})
    result=dict(zones=zones,n=len(raw),physical=phys,work=work,panel_hist=dict(Counter(map(int,base))),panel_issues=len(set(ids)),
        panel_cohorts=dict(Counter(byq[q]["cohort"] for q in panel)),prior_timed_match=matched)
    save(D/"results.json",result)
    print(zones["main_clean"])
    print(phys["observed"],phys["uniform"]["all"])
    print(matched)
if __name__=="__main__":analyze()
