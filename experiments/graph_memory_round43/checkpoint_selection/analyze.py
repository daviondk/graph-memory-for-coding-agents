"""Independent CPU reconstruction from portable evidence. Needs NumPy, no dataset or model."""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile
import numpy as np

D=Path(__file__).resolve().parent
SEEDS=[13,17,29,37,41];ARMS=['full_rgcn','wo_chunk_adjacency']
MODELS=['R35','R33','canonical_full','canonical_noadj','matched_full','matched_noadj']
METRICS=['full_support_2048','coverage_512','coverage_1024','coverage_2048','recall_5','mrr']
PAIRS=[(0,2),(0,3),(0,4),(0,5),(1,2),(1,3),(1,4),(1,5),(4,2),(5,3)]
NAMES=[MODELS[a]+'/'+MODELS[b] for a,b in PAIRS]
DEV=D/'originals'
def read(p):
 b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def digest(b):return sha256(b).hexdigest()
def same(a,b,tol=3e-12):np.testing.assert_allclose(a,b,atol=tol,rtol=0)

def development():
    imported=read(D/'imports.json');seal=read(DEV/'r34-all-dev.json');choices={}
    plans=[('r34-plan','r34-dev','PROTOCOL_RU.md'),('r37-plan','r37-five-seed','protocol')]
    for plan,doc,key in plans:assert read(DEV/(plan+'.json'))['files'][key]==digest((DEV/(doc+'.txt')).read_bytes())
    for n,(_,h) in imported['originals'].items():
        ext='.txt' if n in ('r34-strict','r34-dev','r37-five-seed') else '.json'
        assert digest((DEV/(n+ext)).read_bytes())==h
    for tag,items in imported['tensors'].items():
        with ZipFile(D/f'dev-{tag}.zip') as z:
            ledger=json.loads(z.read('ledger.json'));native=json.loads(z.read('native-checkpoint.json'));rerun=json.loads(z.read('replay-checkpoint.json'))
            assert digest(z.read('ledger.json'))==seal[f'dev-selection-{tag}.json']==items['dev_log'][1]
            assert len(z.namelist())==19
            by_epoch=ledger['ledger'];ids=None;rows=[]
            for i,e in enumerate(by_epoch):
                raw=z.read(f'metrics-{i}.json.gz');assert e['epoch']==i and digest(raw)==e['outcomes']
                outcomes=json.loads(gzip.decompress(raw));ids=sorted(outcomes) if ids is None else ids
                assert len(ids)==580 and set(ids)==set(outcomes)
                assert digest('\n'.join(ids).encode())==items['dev_ids']
                scores=np.asarray([outcomes[q] for q in ids]);assert np.isin(scores[:,0],[0,1]).all() and ((scores[:,1]>=0)&(scores[:,1]<=1)).all()
                fs,cov=scores.mean(axis=0);same([fs,cov],e['criteria'])
                rows.append({'epoch':i,'recall':e['recall5'],'fs':float(fs),'coverage':float(cov)})
            assert [n['epoch'] for n in native['records']]==list(range(1,16))
            native_winner=max(native['records'],key=lambda e:(e['dev_recall_at_5'],-e['epoch']))
            repeated_winner=max(rows,key=lambda e:(e['recall'],-e['epoch']))
            assert native_winner['epoch']==native['epoch']==ledger['original_epoch']==items['original_epoch']
            assert repeated_winner['epoch']==rerun['epoch']==ledger['repeated_epoch']==items['recalled_epoch']
            for i,m in enumerate(rerun['records'],1):same(m['dev_recall_at_5'],rows[i]['recall'])
            by_budget=max(rows,key=lambda e:(round(e['fs'],12),round(e['coverage'],12),-e['epoch']))
            assert by_budget['epoch']==ledger['selected']['epoch']==items['budget_epoch']
            a,b,c=[items[k] for k in ('canonical','replay_recall','replay_budget')]
            assert a.keys()==b.keys()==c.keys() and len(a)==items['keys']
            assert (a==b)==ledger['same_recall_winner_weights'] and (b==c)==(by_budget['epoch']==repeated_winner['epoch'])
            changes=sum(a[k]!=b[k] for k in a);assert (changes==0)==(a==b)
            choices[tag]={'original':native_winner['epoch'],'replayed_recall':repeated_winner['epoch'],'budget':by_budget['epoch'],
                'same_recall_weights':a==b,'parameters_changed':changes,'parameter_tensors':len(a),'within_replay_dev_fs_delta':by_budget['fs']-repeated_winner['fs'],
                'within_replay_dev_coverage_delta':by_budget['coverage']-repeated_winner['coverage']}
    return choices

def aggregate(vectors,clusters):
    # Draw shared weights once for all models/metrics to preserve paired comparisons.
    n,q,m,k=vectors.shape
    ts,ix=np.unique(clusters,return_inverse=True);c=len(ts);assert c==1207 and q==2000
    counts=np.bincount(ix);delta=np.stack([vectors[:,:,a,:]-vectors[:,:,b,:] for a,b in PAIRS],axis=2)
    summ=np.zeros((n,c,len(PAIRS),k))
    for j in range(n):np.add.at(summ[j],ix,delta[j])
    rg=np.random.default_rng(34091);sg=np.random.default_rng(34092)
    fixed=[];cross=[]
    for _ in range(100):
        draws=rg.integers(c,size=(100,c));weights=np.stack([np.bincount(x,minlength=c) for x in draws]);den=weights@counts
        sample=np.array([(weights@x.reshape(c,-1)).reshape(100,len(PAIRS),k) for x in summ])/den[None,:,None,None]
        fixed.append(sample.mean(axis=0))
        seeds=sg.integers(n,size=(100,n))
        cross.append(sample[seeds,np.arange(100)[:,None]].mean(1))
    ci=[np.quantile(np.concatenate(x),[.025,.975],axis=0) for x in (fixed,cross)]
    estimates={};point=delta.mean((0,1))
    for p,pair in enumerate(NAMES):
        estimates[pair]={metric:{'delta':float(point[p,j]),'conditional_ci':ci[0][:,p,j].tolist(),'crossed_ci':ci[1][:,p,j].tolist()} for j,metric in enumerate(METRICS)}
    return {'means':dict(zip(MODELS,vectors.mean((0,1)).tolist())),'contrasts':estimates}

def run():
    choices=development();raw=[read(D/f'paired-{s}.json.gz') for s in SEEDS]
    sources=read(D/'imports.json')['test_sources']
    for seed,records in zip(SEEDS,raw):
        evidence=sources[str(seed)]
        for variant,numbers in enumerate(([0,1,2,3,4],[0,1,2,5,6])):
            assembled={q:[record[i] for i in numbers] for q,record in records.items()}
            serialized=(json.dumps(assembled,sort_keys=True,separators=(',',':'))+'\n').encode()
            assert digest(serialized)==evidence['json_sha256'][variant]
            source,checksum=evidence['paths'][variant]
            register=read(DEV/('r37-'+['canonical','matched'][variant]+'-manifest.json'))
            assert checksum==register[Path(source).name]
    q=sorted(raw[0]);assert all(set(d)==set(q) for d in raw)
    clusters=[raw[0][key][0] for key in q];assert all([d[key][0] for key in q]==clusters for d in raw)
    data=np.asarray([[d[k][1:] for k in q] for d in raw]);assert data.shape==(5,2000,6,6) and ((data>=0)&(data<=1)).all()
    assert np.isin(data[:,:,:,0],[0,1]).all()
    orig=read(DEV/'r34-final.json');allr=aggregate(data,clusters)
    four=aggregate(data[1:],clusters);two=aggregate(data[-2:],clusters)
    for i,arm in enumerate(ARMS):
        to=[('comparisons',allr),('heldout_seeds_17_to_41',four)]
        for name,a in to:
            for metric in METRICS:
                orig_row=orig['arms'][arm][name][metric];row=a['contrasts'][NAMES[6+i]][metric]
                for key in row:same(row[key],orig_row[key])
    for regimen,offset in [('canonical',0),('matched',2)]:
        src=read(DEV/('r37-'+regimen+'.json'))
        for original,split in [('five',allr),('forward',two)]:
            for i,arm in enumerate(ARMS):
                for candidate,source_name in [('R33','R33_cost_worst'),('R35','R35_oof_3894')]:
                    for metric in METRICS:
                        original_row=src[original]['comparisons'][source_name+'/'+arm][metric]
                        row=split['contrasts'][candidate+'/'+MODELS[2+i+offset]][metric]
                        for key in row:same(row[key],original_row[key])
            for p in range(4):same(split['means'][MODELS[[0,1,2+offset,3+offset][p]]],src[original]['means'][['R35_oof_3894','R33_cost_worst',*ARMS][p]])
    return {'seed_order':SEEDS,'metrics':METRICS,'test_q':len(q),'test_traj':len(set(clusters)),'dev_q':580,'dev_epoch_count':160,
            'dev_outcome_vectors':92800,'dev_choices':choices,'five':allr,'held_17_41':four,'held_37_41':two,
            'per_seed':{str(s):dict(zip(MODELS,v.mean(axis=0).tolist())) for s,v in zip(SEEDS,data)}}

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--write',action='store_true');opts=a.parse_args()
    result=run();f=D/'results.json'
    if opts.write and not f.exists():f.write_bytes((json.dumps(result,indent=2,sort_keys=True)+'\n').encode())
    assert read(f)==result
    print('Audited 160 checkpoint epochs, 92,800 dev vectors, 5 test arrays, 10 tensor comparisons and prior paired intervals.')

