import os
for var in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[var]='1'
import numpy as np
import hashlib,gzip,json
from pathlib import Path
D=Path(__file__).resolve().parent
def read(name):
    p=D/name;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(name):return hashlib.sha256((D/name).read_bytes()).hexdigest()
SEEDS=(13,17,29,37,41)
def analyze(rows,pairs):
    ts,ix=np.unique([r[1] for r in rows],return_inverse=True)
    arms=sorted(rows[0][2]['13'])
    a=np.asarray([[[r[2][str(s)][k] for k in arms] for s in SEEDS] for r in rows],dtype=float)
    delta=np.stack([a[:,:,arms.index(x),:]-a[:,:,arms.index(y),:] for x,y in pairs],axis=2)
    sums=np.zeros((len(ts),*delta.shape[1:]))
    np.add.at(sums,ix,delta);counts=np.bincount(ix)
    rng=np.random.default_rng(430313)
    samples=[]
    for _ in range(100):
        t=rng.integers(len(ts),size=(100,len(ts)))
        w=np.stack([np.bincount(v,minlength=len(ts)) for v in t])
        v=(w@sums.reshape(len(ts),-1)).reshape(100,*delta.shape[1:])/(w@counts)[:,None,None,None]
        inds=rng.integers(5,size=(100,5))
        samples.append(v[np.arange(100)[:,None],inds].mean(axis=1))
    ci=np.quantile(np.concatenate(samples),[.025,.975],axis=0)
    return dict(questions=len(rows),trajectories=len(ts),mu={k:a[:,:,i,:].mean(axis=(0,1)).tolist() for i,k in enumerate(arms)},
                per_seed={str(s):{k:a[:,j,i,:].mean(axis=0).tolist() for i,k in enumerate(arms)} for j,s in enumerate(SEEDS)},
                comparisons=[dict(left=x,right=y,delta=delta[:,:,i,:].mean(axis=(0,1)).tolist(),interval=ci[:,i,:].T.tolist(),
                    wins=int((delta[:,:,i,0]>0).sum()),losses=int((delta[:,:,i,0]<0).sum())) for i,(x,y) in enumerate(pairs)])
if __name__=='__main__':
    receipt=read('score-receipt.json')
    assert receipt['results']==sha('scores.json.gz')
    rows=read('scores.json.gz');arms=('wo_chunk_adjacency','full_rgcn')
    pairs=[(k+'/dp',k+'/firstfit') for k in arms]+[(k+'/dp',k+'/value') for k in arms]+[(k+'/value',k+'/firstfit') for k in arms]+[(k+'/dp',k+'/strict') for k in arms]
    result=analyze(rows,pairs)
    assert len(rows)==2000
    result.update(scores=receipt['results'],metrics=['FS','coverage','tokens'],bootstrap=10000,bootstrap_seed=430313)
    (D/'results.json').write_text(json.dumps(result,sort_keys=True,indent=1)+'\n',encoding='utf8')
    print(result['mu']);print(result['comparisons'][:2])

