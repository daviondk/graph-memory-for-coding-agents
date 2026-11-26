from pathlib import Path
import json
import gzip
import numpy as np

ROOT=Path(__file__).resolve().parent
def analyze():
    runs=json.loads(gzip.decompress((ROOT/'observations.json.gz').read_bytes()))
    meta=json.loads((ROOT/'view-log.json').read_bytes())
    modes=('direct','interval','index')
    qs=sorted(meta['queries'])
    assert len({meta['queries'][q]['tr'] for q in qs})==len(qs)
    mat=np.zeros((len(qs),3))
    count=np.zeros((len(qs),3),int)
    for rep,q,m,n,ns in runs:
        mat[qs.index(q),modes.index(m)]+=ns
        count[qs.index(q),modes.index(m)]+=n
    assert np.array_equal(count[:,0],count[:,1]) and np.array_equal(count[:,0],count[:,2])
    rng=np.random.default_rng(46210)
    ix=rng.integers(len(qs),size=(10000,len(qs)))
    boot=mat[ix].sum(axis=1)
    stats={'warm_requests_per_method':int(count[:,0].sum()),'totals_ms':dict(zip(modes,(mat.sum(axis=0)*1e-6).tolist())),'means_us':dict(zip(modes,(mat.sum(axis=0)/count.sum(axis=0)*.001).tolist())),'ratios':{}}
    for x,y in ((0,2),(1,2),(0,1)):
        stats['ratios'][modes[x]+'/'+modes[y]]={'ratio':float(mat[:,x].sum()/mat[:,y].sum()),'interval':np.quantile(boot[:,x]/boot[:,y],[.025,.975]).tolist()}
    savings=(mat[:,0]-mat[:,2]).sum()/count[:,0].sum()
    stats['build_ms']=meta['build_ns']*1e-6
    stats['break_even_vs_direct_total']=int(np.ceil(meta['build_ns']/savings)) if savings>0 else None
    stats['break_even_average_queries_per_source']=stats['break_even_vs_direct_total']/meta['items'] if savings>0 else None
    print(json.dumps(stats))
    (ROOT/'results.json').write_text(json.dumps(stats,indent=2)+'\n','utf8')
if __name__=='__main__':analyze()
