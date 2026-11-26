"""Paired, trajectory-level bootstrap. Entries are unit-level sums or mean of four trials."""
from common_match import *

ARMS = ("eager", "deferred_ref", "deferred_sql")
CLOCKS = ("process_ns", "wall_ns", "thread_cycles")
SEED = 360613

def paired_ratio(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    rng = np.random.default_rng(SEED)
    ratios, diffs = [], []
    for _ in range(100):
        idx = rng.integers(len(a), size=(100, len(a)))
        av, bv = a[idx].sum(axis=1), b[idx].sum(axis=1)
        ratios.extend(av/bv)
        diffs.extend((av-bv)/len(a))
    return dict(ratio=float(a.sum()/b.sum()), ci95=np.quantile(ratios,[.025,.975]).tolist(),
                mean_paired_delta=float((a-b).mean()), delta_ci95=np.quantile(diffs,[.025,.975]).tolist(),
                units=len(a))

def analyze():
    seals = load(D/"counter-seal.json")
    plan = load(D/"plan.json")
    hist={}
    for name,h in sorted(seals["files"].items()):
        assert sha(D/name)==h
        shard=load(D/name)
        assert not set(shard)&set(hist)
        hist.update(shard)
    tids=sorted(hist)
    assert len(tids)==1207
    def col(key):
        return np.array([hist[t]["counts"].get(key,0) for t in tids])
    totals=dict(sum((Counter(v["counts"]) for v in hist.values()),Counter()))
    for key in {"invisible_source_saved"}:
        totals[key]=int(col(key).sum())
    pairs=[("predicates","predicate_new","predicate_old"),("dict_visits","scanned_new","scanned_old"),
           ("reread_call_fraction","lookups","calls"),("reread_raw_fraction","lookup_raw_bytes","all_raw_bytes"),
           ("reread_struct_fraction","lookup_structured_bytes","all_structured_bytes")]
    counters={n:paired_ratio(col(a),col(b)) for n,a,b in pairs}
    peaks={key:dict(max=int(col(key).max()),median=float(np.median(col(key))),p95=float(np.quantile(col(key),.95)))
           for key in ("peak_arg_handles","peak_witnesses","integral_arg_handles","integral_witnesses")}
    tset=load(D/"timing-seal.json")
    assert tset["plan"]==seals["plan"]==sha(D/"plan.json")
    assert sha(D/"timings.json.gz")==tset["samples"]
    panel=plan["timed_ids"]; tm=load(D/"timings.json.gz")
    assert set(tm)==set(panel) and len(panel)==96
    for t,v in tm.items():
        assert v["actual_sql_receipts"]==[hist[t]["counts"].get(k,0) for k in ("lookups","lookup_raw_bytes","lookup_structured_bytes")]
    x=np.array([[[r[m] for m in ARMS] for r in tm[t]["measurements"]] for t in panel])
    assert x.shape==(96,4,3,3)
    avg=x.mean(axis=1)
    timings={}
    for i,m in enumerate(ARMS):
        timings[m]={}
        for j,c in enumerate(CLOCKS):
            timings[m][c]=dict(summed=float(avg[:,i,j].sum()),zero_trials=int(np.sum(x[:,:,i,j]==0)),
                                 min_nonzero=int(x[:,:,i,j][x[:,:,i,j]>0].min()))
            if i:
                timings[m][c]["vs_eager"]=paired_ratio(avg[:,i,j],avg[:,0,j])
            if i==2:
                timings[m][c]["vs_ref"]=paired_ratio(avg[:,i,j],avg[:,1,j])
    out=dict(totals=totals,counter_contrasts=counters,peaks=peaks,
             timing=timings,summed_actual_sql_receipts=np.array([v["actual_sql_receipts"] for v in tm.values()]).sum(axis=0).tolist(),
             all_cut_checks=sum(len(v["cuts"]) for v in hist.values()), equivalent_trajectories=len(hist),
             panel=len(panel), paired_bootstrap_seed=SEED)
    put(D/"summary.json",out)
    return out

if __name__=="__main__":
    analyze()
