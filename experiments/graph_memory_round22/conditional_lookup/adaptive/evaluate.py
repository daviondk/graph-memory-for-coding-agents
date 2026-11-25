"""Open OOF results only after every fold's probabilities and choices are sealed."""
from collections import Counter
from pathlib import Path
from crossfit import predict_probability, np
from freeze import D, ROOT, read, dump, digest


def aggregate(rows):
    n=len(rows);names=['adaptive','neighbor','hybrid','bm25']
    groups=sorted({r['comp'] for r in rows})
    index={name:i for i,name in enumerate(groups)}
    ci={}
    ds=np.array([[r['arms'][names[0]]['hit2']-r['arms'][k]['hit2'] for k in names[1:]] for r in rows])
    grouped=np.zeros((len(groups),3));counts=np.zeros(len(groups))
    for r,v in zip(rows,ds,strict=True):
        g=index[r['comp']];grouped[g]+=v;counts[g]+=1
    rng=np.random.default_rng(2220);pick=rng.integers(0,len(groups),size=(10000,len(groups)))
    values=grouped[pick].sum(1)/counts[pick].sum(1)[:,None]
    for i,k in enumerate(names[1:]):
        ci[k]=dict(delta_pp=float(100*ds[:,i].mean()),ci95_pp=(100*np.quantile(values[:,i],[.025,.975])).tolist(),
                   wins=int((ds[:,i]>0).sum()),losses=int((ds[:,i]<0).sum()),ties=int((ds[:,i]==0).sum()))
    arms={}
    for k in names:
        arms[k]=dict(hit2=sum(r['arms'][k]['hit2'] for r in rows),hit1=sum(r['arms'][k]['hit1'] for r in rows),
              mean_return_bytes=float(np.mean([r['arms'][k]['bytes'] for r in rows])))
    return dict(n=n,components=len(groups),arms=arms,fixed_oof_contrasts=ci,choices=Counter(r['choice'] for r in rows),
                distinct_options=sum(r['options_distinct'] for r in rows))


def refit_bootstrap(xs, rows):
    # All contributing component draws are copied/withheld together. Weights
    # need not be expanded into duplicate rows; the penalized loss sums over rows.
    groups=sorted({r['comp'] for r in rows});gix={g:i for i,g in enumerate(groups)}
    idx=np.array([gix[r['comp']] for r in rows]);fold=np.array([r['fold'] for r in rows])
    models=['neighbor','hybrid','bm25']
    scores=np.array([[r['arms'][m]['hit2'] for m in models] for r in rows])
    diff=scores[:,0]-scores[:,1];X=np.array([xs[r['id']]['x'] for r in rows])
    train=[np.flatnonzero((diff!=0)&(fold!=k)) for k in range(5)]
    test=[np.flatnonzero(fold==k) for k in range(5)]
    def run(w):
        prob=np.zeros(len(rows))
        for tr,te in zip(train,test,strict=True):
            prob[te],_=predict_probability(X[tr],(diff[tr]>0).astype(int),w[tr],X[te])
        chosen=np.where(prob>=.5,scores[:,0],scores[:,1])
        return ((chosen[:,None]-scores)*w[:,None]).sum(0)/w.sum(),prob
    _,check=run(np.ones(len(rows)))
    assert np.max(np.abs(check-np.array([r['p'] for r in rows])))<1e-7
    rand=np.random.default_rng(2221)
    samples=[]
    for _ in range(1000):
        count=np.bincount(rand.integers(0,len(groups),size=len(groups)),minlength=len(groups))
        ds,_=run(count[idx])
        samples.append(ds)
    M=np.array(samples)
    return {m:dict(ci95_pp=(100*np.quantile(M[:,i],[.025,.975])).tolist(),
                        bootstrap_mean_pp=float(100*M[:,i].mean())) for i,m in enumerate(models)}


def main():
    seal=read(D/'forecast-lock.json');assert seal['code']==digest(D/'crossfit.py') and seal['training']==digest(D/'training-lock.json')
    xs={r['id']:r for r in read(D/'features.json.gz')}
    fixed={}
    for k in range(5):
        m=D/f'model-{k}.json';res=D/f'forecast-{k}.json.gz'
        assert digest(m)==seal['models'][str(k)] and read(m)['forecast']==digest(res)
        for r in read(res):
            assert r['id'] not in fixed and xs[r['id']]['fold']==r['fold']
            assert xs[r['id']]['picks'][r['choice']]==r['addresses'];fixed[r['id']]=r
    source=ROOT/'outcomes.json.gz'
    assert digest(source)==read(D/'training-lock.json')['source_labels']
    outcomes=[]
    for row in sorted(read(source),key=lambda x:x['id']):
        d=row['id'];x=xs[d];f=fixed[d];arms={}
        for name in ('neighbor','hybrid','bm25'):
            s=row['methods'][name]
            assert s['opened'][:2]==x['picks'][name]
            arms[name]=dict(hit2=s['hit2'],hit1=s['hit1'],bytes=s['byte_cost2'])
        arms['adaptive']=arms[f['choice']]
        outcomes.append(dict(id=d,comp=x['comp'],fold=x['fold'],p=f['p_neighbor_if_discordant'],choice=f['choice'],
                             options_distinct=x['picks']['neighbor']!=x['picks']['hybrid'],
                             reachable=row['reachable'],labelled=row['labelled'],arms=arms))
    assert len(outcomes)==449
    dump(D/'outcomes.json.gz',outcomes)
    eligible=[r for r in outcomes if r['reachable']]
    annotated=[r for r in outcomes if r['labelled']]
    totals={'primary':aggregate(eligible),'all_annotated':aggregate(annotated)}
    totals['full_refit_primary']=refit_bootstrap(xs,eligible)
    totals['folds']={}
    for k in range(5):
        p=[r for r in eligible if r['fold']==k]
        totals['folds'][str(k)]={'evaluation':aggregate(p),'training':read(D/f'model-{k}.json')}
    totals['oracle_if_better_policy_known']=sum(max(r['arms'][m]['hit2'] for m in ('neighbor','hybrid')) for r in eligible)
    totals['post_forecast_data']=dict(choices=digest(D/'forecast-lock.json'),labels_source=digest(source),outcomes=digest(D/'outcomes.json.gz'),code=digest(Path(__file__)))
    dump(D/'results.json',totals)
    print(totals['primary'],totals['full_refit_primary'],totals['all_annotated'])

if __name__=='__main__':main()

