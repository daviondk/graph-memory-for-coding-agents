"""Paired ratios of summed costs with trajectories resampled jointly across plans."""
import os
for var in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):os.environ[var]='1'
import argparse
from pathlib import Path
import numpy as np
from common44 import D,load,save,sha
from operators import ARMS

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);out=ap.parse_args().out
    seal=load(out/'run-seal.json')
    for p,h in seal['records'].items():assert sha(out/p)==h
    fields=['write','read','mixed','validation','reopened_terminal','repeat_terminal']
    x=np.empty((2,2,1207,len(ARMS),len(fields)),dtype=np.float64)
    physical={};individual={}
    for ri,reads in enumerate((1,4)):
        for rep in range(2):
            r=load(out/f'run-{rep}-{reads}.json.gz')
            for j,arm in enumerate(ARMS):
                v=np.asarray(r['clocks'][arm])
                x[ri,rep,:,j,:]=np.column_stack([v[:,0],v[:,1],v[:,0]+v[:,1],v[:,2:]])
                p=r['info'][arm]
                physical.setdefault(arm,[]).append({k:p[k] for k in ('file_bytes','objects','free_pages','pages','wal_before','checkpoint_ns','setup_ns','reopen_ns')})
                individual[f'{reads}/{rep}/{arm}']=x[ri,rep,:,j,:].sum(axis=0).astype('int64').tolist()
    # Sum both repetitions per trajectory before resampling. Both workloads and all plans share draws.
    obs=x.sum(axis=1);sums=obs.sum(axis=1)
    contrasts=[('pair','ends'),('scan','ends'),('sql_group','ends'),('co','ends'),('co','scan'),('pair','scan')]
    i1=[ARMS.index(a) for a,b in contrasts];i2=[ARMS.index(b) for a,b in contrasts]
    ratio=sums[:,i1,:]/sums[:,i2,:]
    rng=np.random.default_rng(4400771)
    flat=obs.transpose(1,0,2,3).reshape(len(obs[0]),-1)
    boots=[]
    for _ in range(100):
        draws=rng.multinomial(len(flat),np.full(len(flat),1/len(flat)),size=100)
        summed=(draws@flat).reshape(100,2,len(ARMS),len(fields))
        boots.append(summed[:,:,i1,:]/summed[:,:,i2,:])
    lo,hi=np.quantile(np.concatenate(boots),[.025,.975],axis=0)
    ratios={}
    for r,reads in enumerate((1,4)):
        ratios[str(reads)]={}
        for j,(a,b) in enumerate(contrasts):
            ratios[str(reads)][a+'/'+b]={k:[ratio[r,j,i],lo[r,j,i],hi[r,j,i]] for i,k in enumerate(fields)}
    fixture=load(D/'normalized.json.gz');counts={'traces':len(fixture),'boundaries':0,'nonempty':0,'adds':0,'retracts':0,'live_bits':0}
    for tr in fixture:
        for ds,fs in tr:
            counts['boundaries']+=1;counts['nonempty']+=bool(ds)
            counts['adds']+=sum(s>0 for _,_,s in ds);counts['retracts']+=sum(s<0 for _,_,s in ds)
            counts['live_bits']+=sum(bits.bit_count() for _,bits in fs)
    extraction=np.array(load(D/'extraction-times.json.gz'),dtype=np.int64)
    save(out/'results.json',dict(rng=4400771,draws=10000,fields=fields,counts=counts,ratios=ratios,physical=physical,
        timing_ns_per_repetition=individual,extraction_sums_ns=extraction.sum(axis=0).tolist(),
        run=sha(out/'run-seal.json'),fixture=sha(D/'fixture-seal.json')))
    for n,g in ratios.items():
        for arm,v in g.items():print(n,arm,*[tuple(round(w,3) for w in v[k]) for k in fields[:3]])

if __name__=='__main__':main()
