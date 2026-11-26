"""Trajectory bootstrap for the paired warm operator timings."""
from pathlib import Path
import gzip,hashlib,json
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import numpy as np
D=Path(__file__).resolve().parent
def read(path):
    b=path.read_bytes();return json.loads(gzip.decompress(b) if path.suffix=='.gz' else b)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    rows={}
    for i in range(8):
        p=D/f'trace-{i}.json.gz';r=read(p);seal=read(D/f'shard-{i}.json')
        assert sha(p)==seal['sha'] and seal['code']==sha(D/'flow.py') and not rows.keys()&r.keys();rows.update(r)
    assert len(rows)==1207
    totals={k:sum(r['counts'].get(k,0) for r in rows.values()) for k in sorted({k for r in rows.values() for k in r['counts']})}
    assert totals['official_questions']==2000 and totals['official_candidate_rows']==136892
    keys=('PairTable','EndpointSums')
    timing=np.array([[np.array([v[k][:2] for v in rows[t]['timing']]).sum(axis=0) for k in keys] for t in sorted(rows)],dtype=float)
    def ratio(z):
        z=np.concatenate((z,z.sum(axis=-1,keepdims=True)),axis=-1)
        return z[...,0,:]/z[...,1,:]
    rng=np.random.default_rng(440011);boot=[]
    for j in range(100):
        sample=rng.integers(len(rows),size=(100,len(rows)))
        boot.append(ratio(timing[sample].sum(axis=1)))
    paired=np.quantile(np.concatenate(boot),[.025,.975],axis=0).T.tolist()
    out=dict(totals=totals,trajectories=len(rows),traces_with_stale=sum(r['counts']['stale_flags_monotone']>0 for r in rows.values()),
        time_ns_sums=timing.sum(axis=0).tolist(),ratios=ratio(timing.sum(axis=0)).tolist(),intervals=paired,metrics=['write','read-all','combined'],
        baselines=keys,replicates=10000,rng=440011,shards={i:sha(D/f'shard-{i}.json') for i in range(8)})
    (D/'results.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf8')
    print(totals);print(out['traces_with_stale'],out['ratios'],paired)
if __name__=='__main__':main()
