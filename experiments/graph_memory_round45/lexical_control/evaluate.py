"""Calculate paired and group-interaction intervals using shared cluster and seed draws."""
from pathlib import Path
import os
for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[key]='1'
import gzip
import hashlib
import json
import numpy as np

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parents[1]/'graph_memory_round44/flow_support/question-strata.json.gz'
def read_gz(path):
    return json.loads(gzip.decompress(path.read_bytes()))
def run():
    record=json.loads((ROOT/'label-lock.json').read_text('utf8'))
    flag_path=ROOT/'strata.json.gz'
    assert hashlib.sha256(flag_path.read_bytes()).hexdigest()==record['strata_sha256']
    flags=read_gz(flag_path)
    base=[r for r in read_gz(SOURCE) if not r['pilot'] and r['available']==r['full']]
    groups,indices=np.unique([r['t'] for r in base],return_inverse=True)
    assert len(base)==901 and len(groups)==657
    counts=np.zeros((len(groups),2),int)
    sums=np.zeros((len(groups),2,5))
    result={}
    kept=[]
    for group, name in enumerate(('no_identifier','identifier')):
        subset=[(i,r) for i,r in enumerate(base) if flags[r['q']]==bool(group)]
        index=[indices[i] for i,r in subset]
        arms=np.asarray([[r['fs']['value'],r['fs']['rich']] for _,r in subset],float).reshape(-1,2,5)
        delta=arms[:,0]-arms[:,1]
        if len(subset):
            np.add.at(counts[:,group],index,1)
            np.add.at(sums[:,group,:],index,delta)
        result[name]={'n':len(subset),'trajectories':len(set(index)),'full_cohort_n':sum(v==bool(group) for v in flags.values()),'value':float(arms[:,0].mean()) if len(subset) else None,'rich':float(arms[:,1].mean()) if len(subset) else None,'delta':float(delta.mean()) if len(subset) else None}
        for _,r in subset:
            kept.append([r['q'],r['t'],group,r['fs']['value'],r['fs']['rich']])
    rng=np.random.default_rng(450507)
    for _ in range(100):
        draws=rng.integers(len(groups),size=(100,len(groups)))
        weight=np.stack([np.bincount(v,minlength=len(groups)) for v in draws])
        denominator=weight @ counts
        total=(weight @ sums.reshape(len(groups),10)).reshape(100,2,5)
        vals=np.divide(total,denominator[:,:,None],out=np.full_like(total,np.nan),where=denominator[:,:,None]>0)
        seeds=rng.integers(5,size=(100,5))
        estimates=vals[np.arange(100)[:,None],:,seeds].mean(axis=1)
        if _==0: batches=[]
        batches.append(estimates)
    boot=np.concatenate(batches)
    for i,name in enumerate(('no_identifier','identifier','difference_no_minus_ident')):
        if i==2:
            sample=boot[:,0]-boot[:,1]
            d=[result[k]['delta'] for k in ('no_identifier','identifier')]
            result[name]={'delta':d[0]-d[1] if None not in d else None}
        else:
            sample=boot[:,i]
        valid=sample[np.isfinite(sample)]
        result[name]['nonempty_bootstraps']=len(valid)
        result[name]['ci']=np.quantile(valid,[.025,.975]).tolist() if len(valid) else None
    out={'groups':result,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'label_lock_sha256':hashlib.sha256((ROOT/'label-lock.json').read_bytes()).hexdigest(),'n_bootstrap':10000,'seed':450507}
    (ROOT/'paired.json.gz').write_bytes(gzip.compress(json.dumps(kept,separators=(',',':')).encode(),mtime=0))
    (ROOT/'results.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result))
if __name__=='__main__': run()
