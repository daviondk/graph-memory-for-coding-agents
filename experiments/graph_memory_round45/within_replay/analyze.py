"""Clustered paired bootstrap with a shared trajectory and seed draw across both selections."""
import os
for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):os.environ[key]='1'
import argparse,gzip,json
from hashlib import sha256
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent;SEEDS=[13,17,29,37,41];ARMS=['full_rgcn','wo_chunk_adjacency']
METRICS=['fs2048','coverage512','coverage1024','coverage2048','span_coverage_top5','span_mrr','tokens2048']
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return sha256(p.read_bytes()).hexdigest()
def run():
    raw=read(D/'scores.json.gz');seal=read(D/'grade-seal.json')
    assert seal['scores']==sha(D/'scores.json.gz') and seal['forecasts']==sha(D/'forecast-seal.json')
    reg=read(D/'registration.json')['pairs']
    ids=sorted(raw);clusters=[raw[q][0] for q in ids];names,idx=np.unique(clusters,return_inverse=True)
    assert len(ids)==2000 and len(names)==1207
    means={};per={};shifts={};qa={};mat=[]
    for a in ARMS:
        sel={};per[a]={}
        for which in ('recall','matched','gpu_matched','gpu_canonical'):
            def row(q,s):
                value=raw[q][1][str(s)][a][which]
                return value if which.startswith('gpu') else value[0]+[value[1]]
            sel[which]=np.array([[row(q,s) for q in ids] for s in SEEDS])
            means[a+'/'+which]=sel[which].mean((0,1)).tolist()
        matched=sel['matched'];recall=sel['recall'];diff=matched-recall;mat.append(diff)
        eq=matched[:,:,:6]-sel['gpu_matched']
        qa[a]={'fs_matches':int((eq[:,:,0]==0).sum()),'all_six_match':int(np.all(np.abs(eq)<1e-12,axis=-1).sum()),'max_backend_mean_delta':float(np.abs(eq.mean(axis=(0,1))).max())}
        for i,s in enumerate(SEEDS):
            epochs=reg[f'{s}-{a}'];r,b=epochs['recall'],epochs['budget'];delta=diff[i,:,0]
            if r==b:assert (diff[i]==0).all()
            per[a][str(s)]={'recall_epoch':r,'budget_epoch':b,'recall_fs':float(recall[i,:,0].mean()),'budget_fs':float(matched[i,:,0].mean()),
                'wins':int((delta>0).sum()),'losses':int((delta<0).sum()),'delta':diff[i].mean(0).tolist()}
        shifts[a]={'recall_vs_canonical_gpu':(recall[:,:,:6]-sel['gpu_canonical']).mean((0,1)).tolist(),'budget_vs_canonical_gpu':(matched[:,:,:6]-sel['gpu_canonical']).mean((0,1)).tolist()}
    values=np.stack(mat,axis=2);counts=np.bincount(idx);n=len(names);g=np.zeros((5,n,14))
    for i in range(5):np.add.at(g[i],idx,values[i].reshape(len(ids),14))
    tg=np.random.default_rng(34091);sg=np.random.default_rng(34092);fixed=[];cross=[]
    for _ in range(100):
        draw=tg.integers(n,size=(100,n));w=np.stack([np.bincount(v,minlength=n) for v in draw])
        draws=np.array([w@part for part in g])/(w@counts)[None,:,None]
        fixed.extend(draws.mean(0));s=sg.integers(5,size=(100,5))
        cross.extend(draws[s,np.arange(100)[:,None]].mean(1))
    lo,hi=np.quantile(fixed,[.025,.975],axis=0).reshape(2,2,7);lo2,hi2=np.quantile(cross,[.025,.975],axis=0).reshape(2,2,7)
    delta=values.mean((0,1));comp={a:{k:{'delta':float(delta[i,j]),'conditional_ci':[lo[i,j],hi[i,j]],'crossed_ci':[lo2[i,j],hi2[i,j]]} for j,k in enumerate(METRICS)} for i,a in enumerate(ARMS)}
    return {'n':len(ids),'traces':len(names),'metrics':METRICS,'means':means,'per_seed':per,'comparisons':comp,'backend':qa,'changes_vs_original_gpu':shifts,'both_lower_bounds_positive':all(comp[a]['fs2048']['crossed_ci'][0]>0 for a in ARMS)}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args();result=run()
    target=D/'results.json'
    if args.write and not target.exists():target.write_bytes((json.dumps(result,indent=2,sort_keys=True)+'\n').encode())
    assert read(target)==result
    print('two architectures, five seeds, shared CPU and 10000 paired bootstrap replicates')

