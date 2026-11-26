"""Freeze a matched family of rankers differing only in cross-event relations."""
from pathlib import Path
import os, sys
for variable in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[variable]='1'
D=Path(__file__).resolve().parent
W=D.parents[1]
BASE=W/'graph_memory_round42/causal_ablation'
sys.path.insert(0,str(BASE))
import models42 as train
from core42 import SEEDS, read, sha, save, firstfit
import numpy as np
ARMS=('rich','value','resource','cross','value_bit','resource_bit','both_bits')
PRIMARY=('value','resource')
def design(semantic,meta,edge,arm):
    base=np.column_stack([semantic,meta])
    if arm=='rich':return base
    columns={'value':[4,5,12,13],'resource':[6,7,14,15],'cross':[4,5,6,7,12,13,14,15]}
    if arm in columns:return np.column_stack([base,edge[:,columns[arm]]])
    bit_columns={'value_bit':[4,5],'resource_bit':[6,7],'both_bits':[4,5,6,7]}
    return np.column_stack([base,(edge[:,bit_columns[arm]]>0).astype(float)])

def predict():
    assert sha(D/'PROTOCOL_RU.md')=='f596c20723afb6c7abbe0652253cb2e9747a4ba89ca5cb2dec8963bf9c36c316'
    inventory=read(BASE/'manifest.json')['files']
    assert all(sha(BASE/f)==inventory[f] for f in ['models42.py','models.json','predict42.py'])
    data,w,stats,*_=train.prepare()
    models={}
    previous=read(BASE/'models.json')['models']
    for arm in ARMS:
        x=design(data['sem13'],data['meta'],data['edge'],arm)
        if arm in ('rich','cross'):
            models[arm]=previous[arm]['hgb']
            compare=train.inputs(data['sem13'],data['meta'],data['edge'],data['sham'],arm)
            assert np.array_equal(compare,x)
        else:models[arm]=train.trees_for(x,data['labels'],w)
    save(D/'weights.json',dict(models=models,train=stats,baseline=sha(BASE/'manifest.json'),code=sha(Path(__file__)),protocol=sha(D/'PROTOCOL_RU.md')))
    hashes={};signals=np.zeros((2,4),int);matches=0
    for sh in range(8):
        packs={}
        prev=read(BASE/f'packets-{sh}.json.gz')
        for stage_idx,stage in enumerate(('train','test')):
            f=BASE/f'{stage}-{sh}.npz';assert sha(f)==inventory[f.name]
            with np.load(f) as inp:
                ed=inp['edge']; val=(ed[:,4:6]>0).any(axis=1);res=(ed[:,6:8]>0).any(axis=1)
                signals[stage_idx]+=np.bincount(val.astype(int)+2*res.astype(int),minlength=4)
                if stage=='train':continue
                records=read(BASE/f'test-{sh}.json.gz');meta=inp['meta'];cost=np.rint(np.expm1(meta[:,1])).astype(int)
                for seed in SEEDS:
                    sem=inp[f'sem{seed}'];rank=np.rint(np.expm1(sem[:,0])).astype(int)
                    preds={arm:train.portable(models[arm],design(sem,meta,ed,arm)) for arm in ARMS}
                    at=0
                    for q,t,n,index in records:
                        ix=np.array(index);sl=slice(at,at+n);at+=n;rr=rank[sl];choices={}
                        for arm in ARMS:
                            order=np.lexsort((rr,-preds[arm][sl]))
                            ids=firstfit(order,cost[sl]);choices[arm]=ix[ids].tolist()
                        for arm in ('rich','cross'):
                            assert choices[arm]==prev[q][1][str(seed)]['hgb/'+arm]
                            matches+=1
                        packs.setdefault(q,[t,{}])[1][str(seed)]=choices
                    assert at==len(cost)
        dest=D/f'packets-{sh}.json.gz';save(dest,packs);hashes[dest.name]=sha(dest)
    assert matches==20000
    save(D/'predictions.json',dict(inputs=sha(BASE/'manifest.json'),models=sha(D/'weights.json'),files=hashes,baseline_matches=matches,
        nonzero_rows=dict(train=signals[0].tolist(),test=signals[1].tolist(),columns=['neither','value_only','resource_only','both'])))

def grade():
    sys.path.insert(0,str(W/'graph_memory_round33/budget_loss'))
    import data as src
    seal=read(D/'predictions.json')
    atoms=read(W/'graph_memory_round34/interval_witness/test-atoms.json.gz')
    gold=read(src.nm.OFF/'gold-spans.json.gz')
    old={r['q']:r for r in read(BASE/'scores.json.gz')}
    outcomes=[];checked=0
    for sh,file in enumerate(src.sources('test')):
        pp=D/f'packets-{sh}.json.gz';assert sha(pp)==seal['files'][pp.name]
        packs=read(pp)
        for row in read(file):
            q,t=row['q'],row['t'];prior=old[q];assert t==packs[q][0]==prior['t']
            nodes=[src.nm.pilot.RankedNodeRecord.model_validate(x) for x in row['rr']]
            truth=tuple(src.nm.pilot.SourceSpan.model_validate(x) for x in gold[q])
            spans=[(hi-lo,set(ids)) for _,lo,hi,ids in atoms[q]];total=sum(k for k,_ in spans)
            cache={};vals={}
            for seed in SEEDS:
                scores={}
                for arm,seq in packs[q][1][str(seed)].items():
                    key=tuple(seq)
                    if key not in cache:
                        ids=set(seq);assert len(ids)==len(seq)
                        n=sum(k for k,block in spans if ids&block)
                        candidates=tuple(nodes[i] for i in seq);cost=sum(node.token_count for node in candidates)
                        metric=src.nm.pilot.span_metrics_under_token_budget(candidates,truth,2048)
                        assert cost<=2048 and (n==total)==metric.full_support and abs(n/total-metric.coverage)<1e-12
                        cache[key]=[int(n==total),n/total,cost]
                    scores[arm]=cache[key]
                for arm in ('cross','rich'):assert scores[arm]==prior['arms'][str(seed)]['hgb/'+arm]
                vals[str(seed)]=scores
            outcomes.append(dict(q=q,t=t,pilot=prior['pilot'],eligible=prior['eligible'],arms=vals));checked+=len(cache)
    save(D/'outcomes.json.gz',outcomes)
    save(D/'evaluation.json',dict(forecast=sha(D/'predictions.json'),outcomes=sha(D/'outcomes.json.gz'),unique_checks=checked,questions=len(outcomes)))

if __name__=='__main__':
    {'predict':predict,'grade':grade}[sys.argv[1]]()
