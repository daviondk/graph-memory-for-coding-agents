"""Estimate the pairwise benchmark cost of validating instead of refreshing each observation."""
from collections import defaultdict
from pathlib import Path
from score import ROOT,rr,j,sha,canon,save
def main():
    decisions=rr(ROOT/'decisions.csv')
    oldtr={};oldraw={};newraw={};prov=defaultdict(list)
    for f in (ROOT/'runs').glob('*/*/plain.json'):
        pkg,v=f.parent.parent.name,f.parent.name
        for r in j(f):oldraw[pkg,v,r['key']]=r
        for r in j(f.parent/'traced.json'):oldtr[pkg,v,r['key']]=r
    summary={}
    for group in ['all']+sorted({r['pkg'] for r in decisions}):
        rows=[r for r in decisions if group=='all' or r['pkg']==group]
        def total(f):return sum(f(r) for r in rows)/1e9
        def plain(r,v):return oldraw[r['pkg'],r[v],r['key']]
        def trace(r):return oldtr[r['pkg'],r['old'],r['key']]
        def keep(r):return r['observed_branches_guards']=='True'
        s={'n':len(rows),'saved_calls':sum(keep(r) for r in rows),'old_probe_s':total(lambda r:plain(r,'old')['run_ns']),
           'old_probe_traced_s':total(lambda r:trace(r)['run_ns']),
           'all_new_probe_s':total(lambda r:plain(r,'new')['run_ns']),
           'avoided_new_probe_s':total(lambda r:plain(r,'new')['run_ns']*keep(r)),
           'avoided_new_lookup_and_probe_s':total(lambda r:(plain(r,'new')['run_ns']+plain(r,'new')['load_ns'])*keep(r))}
        s['old_tracing_extra_s']=s['old_probe_traced_s']-s['old_probe_s']
        summary[group]=s
    s=summary['all']
    overhead=j(ROOT/'prediction_lock.json')['selection_seconds']
    # This upstream code actually runs all six derived policies together and some work is shared.
    s['all_signature_policy_validation_seconds']=overhead
    s['illustrative_break_even_ms_per_avoided_expensive_probe']=1000*(overhead+s['old_tracing_extra_s'])/s['saved_calls']
    s['extra_cpu_wall_s_paired_trace_and_validation_less_avoided_probe']=overhead+s['old_tracing_extra_s']-s['avoided_new_probe_s']
    for pkg in sorted({r['pkg'] for r in decisions}):
        rows=[r for r in decisions if r['pkg']==pkg]
        for r in rows:
            meta=oldtr[pkg,r['old'],r['key']]
            prov[pkg].append(len(canon({'entry':meta['entry'],'covered':meta['covered']}).encode()))
    for pkg,lens in prov.items():summary[pkg]['archived_debug_provenance_mean_bytes']=sum(lens)/len(lens)
    save(ROOT/'economics.json',summary);print(s)
if __name__=='__main__':main()

