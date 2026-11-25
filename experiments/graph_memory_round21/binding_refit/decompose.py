"""Post hoc arithmetic decomposition of the already frozen two-by-two comparisons."""
from collections import defaultdict
from pathlib import Path
import sys
from refit import D,INCR,read,save,sha
import numpy as np

def summary(rs):
    if not rs: return {}
    groups=defaultdict(list)
    for r in rs:
        y=r['arms']
        xx,xa,ax,aa=[y[k]['fs'] for k in ('exact/exact','exact/append','append/exact','append/append')]
        fit=.5*((xx-ax)+(xa-aa))
        topology=.5*((xx-xa)+(ax-aa))
        values=[xx-aa,topology,fit,(xx-xa)-(ax-aa)]
        assert xx-aa==fit+topology
        groups[r['t']].append(values)
    arr=np.array([np.sum(group,axis=0) for _,group in sorted(groups.items())])
    sizes=np.array([len(group) for _,group in sorted(groups.items())])
    rng=np.random.default_rng(2119);samples=[]
    for _ in range(40):
        ix=rng.integers(0,len(arr),size=(250,len(arr)))
        samples.extend(arr[ix].sum(axis=1)/sizes[ix].sum(axis=1)[:,None])
    ci=np.quantile(samples,[.025,.975],axis=0)
    return dict(n=len(rs),t=len(groups),estimates={k:dict(net=float(arr[:,j].sum()),pp=float(100*arr[:,j].sum()/len(rs)),ci_pp=(100*ci[:,j]).tolist()) for j,k in enumerate(('diagonal','read_state','fit_state','interaction'))})

def main():
    audit=read(INCR/'readout-graph-audit.json.gz')
    source=read(INCR/'readout-lock.json')
    assert source['graph_audit']==sha(INCR/'readout-graph-audit.json.gz')
    extra={r['t']:r['extra'] for r in audit}
    rows=[r for r in read(D/'test-outcomes.json.gz') if not r['pilot']]
    bins={'all':rows,'retired_edge_present':[r for r in rows if extra[r['t']]],'no_retired_edges':[r for r in rows if not extra[r['t']]]}
    result={k:summary(v) for k,v in bins.items()}
    assert result['no_retired_edges']['estimates']['read_state']['net']==0
    save(D/'decomposition.json',dict(type='post-hoc symmetric decomposition of 2x2 finite table; sampling uncertainty clustered by trajectory',panels=result,inputs=[source['graph_audit'],sha(D/'test-outcomes.json.gz')]))
    print({k:(v['n'],v['t'],{j:round(x['pp'],3) for j,x in v['estimates'].items()}) for k,v in result.items()})
if __name__=='__main__':main()

