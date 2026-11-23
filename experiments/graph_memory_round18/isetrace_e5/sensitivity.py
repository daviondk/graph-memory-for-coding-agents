"""Summarize every memory mode and the pre-existing R17-exclusion sensitivity cohort."""
from collections import defaultdict
from statistics import mean
from project import ROOT,OFF,load,put,pilot
from placebo import cluster_ci
def run():
    rows=load(ROOT/'outcomes.json.gz')
    cq={r['query_id']:r for r in load(OFF/'cohort.json')}
    base=OFF.parents[1]/'graph_memory_round17/isetrace';old=set()
    for f in [base/'cohort.json',base/'replication/cohort.json']:old.update(load(f)['selected'])
    assert len(old)==128
    index=defaultdict(dict)
    for r in rows:
        if r['group']=='main':index[r['q']][r['arm']]=r
    panels={'outside_R17_trajectories':[q for q in cq if cq[q]['trajectory_id'] not in old],
            **{'mode/'+str(mode):[q for q in cq if cq[q]['memory_mode']==mode] for mode in sorted({r['memory_mode'] for r in cq.values()})}}
    res={}
    for panel,qs in panels.items():
        summ={}
        for arm in ('prefix','clip','skip','value','related'):
            obs=[index[q][arm] for q in qs]
            summ[arm]={k:mean(r[k] for r in obs) for k in ('full_support','coverage','tokens')}
        comp={}
        for arm in ('prefix','skip'):
            ds=[(cq[q]['trajectory_id'],index[q]['related']['full_support']-index[q][arm]['full_support']) for q in qs]
            comp[arm]=dict(delta=mean(v for _,v in ds),cluster_ci=cluster_ci(ds))
        res[panel]=dict(n=len(qs),n_traj=len(set(cq[q]['trajectory_id'] for q in qs)),arms=summ,related_minus=comp)
    put(ROOT/'sensitivity.json',res)
if __name__=='__main__':run()
