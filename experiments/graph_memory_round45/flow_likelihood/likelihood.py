"""Fit question-balanced, role/rank-conditional flag frequencies using signed train rows."""
from common45 import *
import numpy as np

def axes(sem,meta,edge):
    rank=np.rint(np.expm1(sem[:,0])).astype(int)
    role=meta[:,0].astype(int)
    assert np.min(rank)>=1 and np.isin(role,[0,1]).all()
    stratum=5*role+np.searchsorted([1,4,16,64],rank,side='left')
    bits=(edge[:,4]>0).astype(int)+2*(edge[:,5]>0).astype(int)
    return rank,stratum,bits

def fit():
    check_registration()
    base=read(R42/'manifest.json')['files']
    counts=np.zeros((10,2,4));examples=np.zeros_like(counts,dtype=int);total=used=0
    for sh in range(8):
        fp=R42/f'train-{sh}.npz';rp=R42/f'train-{sh}.json.gz'
        assert sha(fp)==base[fp.name] and sha(rp)==base[rp.name]
        with np.load(fp) as z:
            _,s,b=axes(z['sem13'],z['meta'],z['edge'])
            y=z['labels'].astype(int);at=0
            for q,t,n,_ in read(rp):
                sl=slice(at,at+n);at+=n;total+=1
                yy=y[sl];mass=np.bincount(yy,minlength=2)
                if min(mass)==0:continue
                used+=1;w=.5/mass[yy]
                np.add.at(counts,(s[sl],yy,b[sl]),w)
                np.add.at(examples,(s[sl],yy,b[sl]),1)
            assert at==len(y)
    assert used==1966 and total==3894 and np.allclose(counts.sum(axis=(0,2)),used/2)
    pool=counts.sum(axis=1);prior=(pool+.25)/(pool.sum(axis=1,keepdims=True)+1)
    probs=(counts+4*prior[:,None,:])/(counts.sum(axis=2,keepdims=True)+4)
    offsets=np.log(probs[:,1,:]/probs[:,0,:]);offsets[(pool>0).sum(axis=1)<2]=0
    save(D/'table.json',dict(counts=counts.tolist(),examples=examples.tolist(),log_ratio=offsets.tolist(),
        probability=probs.tolist(),questions=total,informative=used,alpha=4,fit=sha(D/'likelihood.py'),
        registration=sha(D/'registration.json')))
    print('table sealed',sha(D/'table.json'),flush=True)

if __name__=='__main__':fit()
