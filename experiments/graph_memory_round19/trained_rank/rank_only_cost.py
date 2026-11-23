"""Measure post-ranking repacking with source coordinates from the real R18 PU rankings."""
import hashlib,time
from statistics import median
from prepare import ROOT,R18,OFF,load,put,pilot
from placebo import make_groups,package
def run():
    s=time.perf_counter();meta=load(OFF/'placebo-event-metadata.json.gz');allq=[];seed=R18/'isetrace_e5';seal=load(seed/'forecast-seal.json');num=0
    for f,h in seal['forecasts'].items():
        if not f.startswith('forecasts-main-'):continue
        assert pilot.sha(seed/f)==h
        for r in load(seed/f):
            rr=r['rr'];shape,_,_=make_groups(rr,meta[r['t']]);order=[n['node_id'] for n in rr]
            allq.append((order,r['arms']['prefix'],shape,r['arms']['related']));num+=len(order)
    load_s=time.perf_counter()-s;dur=[]
    for repeat in range(5):
        s=time.perf_counter()
        for order,prefix,shape,expected in allq:
            assert package(order,prefix,shape,{})==expected
        dur.append(time.perf_counter()-s)
    put(ROOT/'rank-only-cost.json',dict(surrogate='R18 native frozen E5 ranks, measured directly. No original author R-GCN predictions supplied.',q=len(allq),
        scored_candidates=num,decode_validate_prepare_source_metadata_seconds=load_s,related_pack_five_durations_seconds=dur,
        median_pack_seconds=median(dur),num_verified_picks=len(allq)*len(dur)))
if __name__=='__main__':run()
