"""Estimates depend only on graph counts, not question or answer labels."""
from panel import *
from collections import Counter
import numpy as np
def boot(v,seed):
    x=np.asarray(v,dtype=float);rng=np.random.default_rng(seed);obs=x[:,4];den=x[:,3]+obs;pop=len(x);br=[];bp=[];be=[]
    for _ in range(100):
        ix=rng.integers(0,pop,size=(100,pop));numer=obs[ix].sum(axis=1);d=den[ix].sum(axis=1);br.extend(np.divide(numer,d,where=d>0,out=np.full(100,np.nan)));bp.extend((obs[ix]>0).mean(axis=1));be.extend((den[ix]>0).mean(axis=1))
    return np.array(br),np.array(bp),np.array(be)
def describe(arr,seed):
    x=np.asarray(arr,dtype=np.int64);n=len(x);e,m,l,once,never=x.T;d=once+never;mask=d>0;fr=never[mask]/d[mask];assert np.array_equal(l-e,d);br,bp,be=boot(arr,seed);j=int(np.argmax(d))
    ts=x.sum(axis=0);score=float(never.sum()/d.sum())
    return {"n":n,"sum_E_M_L_once_never":ts.tolist(),"sum_extra":int(d.sum()),"pooled_fraction_never":score,"pooled_95":np.nanquantile(br,[.025,.975]).tolist(),"histories_extra":int(mask.sum()),"no_extra":int((~mask).sum()),"with_never":int((never>0).sum()),"with_once":int((once>0).sum()),"both":int(((once>0)&(never>0)).sum()),"prevalence_never":float(np.mean(never>0)),"prevalence_never_95":np.quantile(bp,[.025,.975]).tolist(),"prevalence_extra_95":np.quantile(be,[.025,.975]).tolist(),"median_fraction_among_extra":float(np.median(fr)),"mean_fraction_among_extra":float(fr.mean()),"ci_draws_nonzero":int(np.isfinite(br).sum()),"single_largest_history":{"extra":int(d[j]),"never":int(never[j]),"fraction_of_all_extra":float(d[j]/d.sum()),"pooled_after_excluding":float((never.sum()-never[j])/(d.sum()-d[j]))}},br
def main():
    plan=load(D/"plan.json");ss=load(D/"run-seal.json");d={};legacy={}
    for sh in range(8):
        p=D/f"histories-{sh}.json.gz";assert sha(p)==ss["parts"][p.name];d.update(load(p));legacy.update(load(P/f"graphs-{sh}.json.gz"))
    assert d.keys()==plan["panel"].keys() and not d.keys()&legacy.keys() and len(legacy)==1207
    status=Counter(z["status"] for z in d.values());rows={t:z for t,z in d.items() if z["status"]=="retained"};res={};comp={}
    for k,cut in enumerate(("25","50","75","100")):
        for level in ("pu","groups"):
            aa=[rows[t]["cuts"][cut][level] for t in sorted(rows)];bb=[]
            for t in sorted(legacy):
                s=legacy[t]["states"][cut]
                if level=="pu":bb.append([s[c] for c in ["exact","material","logical","once_visible","never_visible"]])
                else:
                    e,m,l=[s["logical_pairs"][c] for c in ["E","M","L"]];bb.append([e,m,l,m-e,l-m])
            a,ba=describe(aa,360090+k);b,bbt=describe(bb,360950+k);res[cut+"_"+level]={"unannotated":a,"annotated_test_reference":b};comp[cut+"_"+level]={"descriptive_gap_pp":100*(a["pooled_fraction_never"]-b["pooled_fraction_never"]),"independent_bootstrap_95_pp":(100*np.quantile(ba-bbt,[.025,.975])).tolist()}
    series=list(rows.values());chk={k:sum(z[k] for z in series) for k in ["calls","outputs","event_checks","distinct_cuts","empty_outputs","output_units","parallel","native_prefixes","incomplete_native"]};peaks=np.array([v["memory"] for v in series])
    native={t:d[t]["status"] for t in plan["native"]};nf=[t for t in native if d[t]["status"]=="retained"]
    save(D/"results.json",{"selection":{"drawn":len(d),"statuses":dict(status),"native_status":dict(Counter(native.values())),"overlap_annotated":0,"overlap_official":0},"reconstruction":chk,"native_histories_with_checks":len(nf),"native_pairset_hash_checks":2*chk["native_prefixes"],"memory_counters":{"sum_peak_old":int(peaks[:,0].sum()),"sum_peak_open":int(peaks[:,1].sum()),"sum_old_references_over_events":int(peaks[:,2].sum()),"sum_open_references_over_events":int(peaks[:,3].sum()),"histories_peak_lower_same_higher":[int((peaks[:,1]<peaks[:,0]).sum()),int((peaks[:,1]==peaks[:,0]).sum()),int((peaks[:,1]>peaks[:,0]).sum())]},"panels":res,"contrast":comp,"source_seal":sha(D/"run-seal.json"),"code":sha(D/"analysis.py")});print(status,chk,res["50_pu"],comp["50_pu"],flush=True)
if __name__=="__main__":main()
