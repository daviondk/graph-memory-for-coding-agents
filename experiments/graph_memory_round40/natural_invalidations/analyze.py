"""Paired within-state random-path expectation with issue as the sampling unit."""
from collections import Counter,defaultdict
import numpy as np
from project import D,read,save,sha

KEYS=('actual_changed','random_changed','draw_changed','actual_safe','random_safe','draw_safe')
def summary(rows):
    if not rows:return {'n':0}
    by=defaultdict(list)
    for r in rows:by[r['issue']].append(r)
    matrix=np.asarray([[np.mean([r[k] for r in rs]) for k in KEYS] for _,rs in sorted(by.items())]);delta=matrix[:,0]-matrix[:,1]
    macro=float(delta.mean());ci=None
    if len(by)>=2:
        rng=np.random.default_rng(403901);draw=rng.integers(0,len(by),size=(10000,len(by)));ci=np.quantile(delta[draw].mean(axis=1),[.025,.975]).tolist()
    return dict(n=len(rows),runs=len({r['rid'] for r in rows}),issues=len(by),repos=len({r['repo'] for r in rows}),totals={k:sum(r[k] for r in rows) for k in KEYS},mean_macro={k:float(matrix[:,i].mean()) for i,k in enumerate(KEYS)},delta_macro=macro,ci95=ci,mean_paths=float(np.mean([r['paths'] for r in rows])),mean_units=float(np.mean([r['units'] for r in rows])),mean_bytes=float(np.mean([r['bytes'] for r in rows])),issue_deltas=dict(zip(sorted(by),delta.tolist())))

def main():
    raw=read(D/'observations.json.gz');seal=read(D/'score-seal.json');assert seal['outcomes']==sha(D/'observations.json.gz')
    groups={}
    for group in ('main','additional','pooled'):
        rows=[r for r in raw if group=='pooled' or r['group']==group]
        labels={'all':rows,'multi_active':[r for r in rows if r['paths']>=2 and r['present']], 'multi_absent':[r for r in rows if r['paths']>=2 and not r['present']], 'single_active':[r for r in rows if r['paths']==1 and r['present']], 'single_absent':[r for r in rows if r['paths']==1 and not r['present']], 'empty':[r for r in rows if r['paths']==0], 'all_present':[r for r in rows if r['present']], 'all_absent':[r for r in rows if not r['present']]}
        for status in ('confirmed_replacement','confirmed_other','unconfirmed_attempt'):
            labels[status]=[r for r in rows if r['receipt']==status];labels[status+'_multi_active']=[r for r in labels['multi_active'] if r['receipt']==status]
        groups[group]={k:summary(rs) for k,rs in labels.items()}
    save(D/'results.json',dict(groups=groups,score_seal=sha(D/'score-seal.json'),seeds=dict(draw='r40-natural-path-v1',bootstrap=403901),bootstrap_draws=10000));print({k:(v['multi_active'].get('n'),v['multi_active'].get('issues'),v['multi_active'].get('delta_macro'),v['multi_active'].get('ci95')) for k,v in groups.items()})
if __name__=='__main__':main()
