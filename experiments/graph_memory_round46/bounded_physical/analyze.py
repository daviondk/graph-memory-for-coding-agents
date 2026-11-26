"""Paired ratios of summed duration with the trajectory as the resampling unit."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import argparse,gzip,json
from collections import Counter
from hashlib import sha256
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):return sha256(p.read_bytes()).hexdigest()
def analyze():
    reg=read(D/'registration.json');seal=read(D/'run-seal.json')
    assert seal['registration']==sha(D/'registration.json');arms=reg['arms'];metrics=['wall','cpu','write','read','write_read']
    pairs=[('eager','deferred'),('exact','deferred'),('packed','deferred'),('exists','deferred'),('scan','deferred'),('distinct','deferred'),('scan_memo','deferred_memo'),
           ('exact_memo','deferred_memo'),('exact','scan'),('exact_memo','scan_memo'),('scan','scan_memo'),('exact','exact_memo'),('deferred','deferred_memo'),('distinct','scan'),('eager','packed'),('exists','packed')]
    idx1=[arms.index(a) for a,b in pairs];idx2=[arms.index(b) for a,b in pairs]
    totals={};summary={};physical={};cohorts={};reptimes={}
    for k in (1,4):
        times=[];sums=[]
        for rep in range(3):
            fn=f'run-{rep}-{k}.json.gz';assert sha(D/fn)==seal['runs'][fn];r=read(D/fn)
            a=np.array([r['records'][name] for name in arms],dtype=np.int64);assert a.shape==(len(arms),1207,6)
            for name,st in r['storage'].items():
                physical.setdefault(name,[]).append(st)
            duration=np.concatenate([a[:,:,:4],a[:,:,2:4].sum(axis=2,keepdims=True)],axis=2)
            times.append(duration);sums.append(a.sum(axis=1))
            reptimes[f'{rep}-{k}']={arm:duration[i].sum(axis=0).tolist() for i,arm in enumerate(arms)}
        t=np.array(times).sum(axis=0).astype(np.float64)
        n=t.shape[1];flat=t.transpose(1,0,2).reshape((n,-1));rng=np.random.default_rng(reg['bootstrap_seed'])
        bs=[]
        for _ in range(100):
            mult=rng.multinomial(n,np.full(n,1/n),size=100)
            z=(mult@flat).reshape(100,len(arms),len(metrics))
            bs.append(z[:,idx1,:]/z[:,idx2,:])
        lo,hi=np.quantile(np.concatenate(bs),[.025,.975],axis=0);a=t.sum(axis=1);estimate=a[idx1]/a[idx2]
        summary[str(k)]={x+'/'+y:{m:[estimate[j,i],lo[j,i],hi[j,i]] for i,m in enumerate(metrics)} for j,(x,y) in enumerate(pairs)}
        totals[str(k)]={arm:{'mean_ms':(a[j]/3e6).tolist(),'probes':int(sums[0][j,4]),'hits':int(sums[0][j,5])} for j,arm in enumerate(arms)}
        assert all(np.array_equal(sums[0][:,4:],z[:,4:]) for z in sums)
        # Replicate-level peak-to-peak spread is reported separately from the trajectory interval.
        cohorts[str(k)]={a+'/'+b:[v[arms.index(a)].sum(axis=0)[0]/v[arms.index(b)].sum(axis=0)[0] for v in times] for a,b in pairs}
    output={'metrics':metrics,'arms':arms,'ratio_definition':'numerator elapsed / denominator elapsed','ratios':summary,'mean_per_pass':totals,
            'physical':physical,'replicate_wall_ratios':cohorts,'per_repetition_ns':reptimes,'draws':10000,'traces':1207,'boundaries':31279,'full_map_checks':31279*len(arms)*(1+4)*3,
            'final_reopened_maps':1207*len(arms)*6,'reference_seal':sha(D/'run-seal.json')}
    return output
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');a=p.parse_args();out=analyze();dest=D/'results.json'
    if a.write and not dest.exists():dest.write_bytes((json.dumps(out,sort_keys=True,indent=2)+'\n').encode())
    assert read(dest)==out
    print('All trajectory-paired duration estimates verified.')

