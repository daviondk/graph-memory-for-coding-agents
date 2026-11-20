"""Score locked predictions against independent navigation and patch endpoints."""
from collections import defaultdict
import random
from pathlib import Path
from forecast import D,PANELS,digest,read,save

CONTRASTS=[('rrf_graph','rrf_strong'),('rrf_graph','rrf_uniform'),('rrf_graph','rrf_shuffled'),
           ('rrf_graph','dense'),('rrf_graph','graph'),('graph','dense'),('dense','dense_issue'),('dense','dense_path')]
METRICS=('h1','h3','mrr')

def observe(k):
    return [int(k==1),int(0<k<=3),1/k if k else 0.]

def agg(rows):
    n=len(rows)
    names=list(rows[0]['ranks'])
    return {'n':n,'tasks':len({r['iid'] for r in rows}),'repos':len({r['repo'] for r in rows}),
        'empty':sum(not r['candidates'] for r in rows),'reachable':sum(r['reachable'] for r in rows),
        'methods':{m:{'h1':sum(r['ranks'][m]==1 for r in rows),'h3':sum(0<r['ranks'][m]<=3 for r in rows),
            'mrr':sum(observe(r['ranks'][m])[2] for r in rows)/n} for m in names}}

def quant(x,p):
    v=sorted(x);z=(len(v)-1)*p;i=int(z)
    return v[i]+(z-i)*(v[min(len(v)-1,i+1)]-v[i])

def contrasts(rows):
    import numpy as np
    ids=sorted({r['iid'] for r in rows});lookup={k:i for i,k in enumerate(ids)}
    cnt=np.bincount([lookup[r['iid']] for r in rows])
    rng=np.random.default_rng(301754)
    bag=rng.multinomial(len(ids),[1/len(ids)]*len(ids),size=5000)
    denom=bag@cnt
    ans={}
    for m,b in CONTRASTS:
        vals=np.array([[u-v for u,v in zip(observe(r['ranks'][m]),observe(r['ranks'][b]))] for r in rows])
        task=np.zeros((len(ids),3))
        for r,v in zip(rows,vals):task[lookup[r['iid']]]+=v
        res=(bag@task)/denom[:,None]
        ans[m+'__minus__'+b]={k:{'delta':float(vals[:,j].mean()),'ci95':[quant(res[:,j],.025),quant(res[:,j],.975)],
                        'wins':int((vals[:,j]>0).sum()),'losses':int((vals[:,j]<0).sum()),
                        'ties':int((vals[:,j]==0).sum())} for j,k in enumerate(METRICS)}
    return ans

def main():
    seal=read(D/'forecast.lock.json')
    assert all(digest(D/n)==sha for n,sha in seal.items())
    forecasts=read(D/'predictions.json.gz')
    summary={};pairs={};evalrows={};sources={}
    for p,d in PANELS.items():
        nav={r['id']:r for r in read(d/'navigation_labels.json.gz')}
        patches={r['iid']:r for r in read(d/'patch_labels.json.gz')}
        orig=read(d/'results.json')['endpoints']
        sources[p]={name:digest(d/name) for name in ('navigation_labels.json.gz','patch_labels.json.gz','results.json')}
        ro=forecasts[p];assert set(nav)=={r['id'] for r in ro}
        rs=defaultdict(list)
        for r in ro:
            label=nav[r['id']]
            patch=patches[r['iid']]
            targets={}
            for field,endpoint in [('target','next'),('plain','plain')]:
                if label[field]:targets[endpoint]={label[field]['path']}
            if patch['status']=='ok' and patch['strict']:
                if patch['prod']:targets['patch']=set(patch['prod'])
                if patch['all_py']:targets['patch_all_py']=set(patch['all_py'])
            candidates=set(r['ranks']['dense'])
            for ep,goal in targets.items():
                ranks={m:next((i+1 for i,t in enumerate(names) if t in goal),0) for m,names in r['ranks'].items()}
                rs[ep].append({'id':r['id'],'iid':r['iid'],'repo':r['repo'],'candidates':len(candidates),
                               'reachable':bool(candidates&goal),'ranks':ranks,'targets':sorted(goal)})
        summary[p]={};pairs[p]={}
        for ep,rows in rs.items():
            s=agg(rows);old=orig[ep]['all']; assert (s['n'],s['tasks'],s['reachable'])==(old['n'],old['tasks'],old['ceiling'])
            for method,sc in old['score'].items():
                for k in METRICS:assert abs(s['methods'][method][k]-sc[k])<1e-9,(p,ep,method,k)
            summary[p][ep]=s
            pairs[p][ep]=contrasts(rows)
        evalrows[p]=rs
    save(D/'evaluation_rows.json.gz',evalrows)
    save(D/'results.json',summary);save(D/'paired.json',pairs)
    save(D/'evaluation.lock.json',{'forecasts':digest(D/'forecast.lock.json'),'source':sources,
             'files':{n:digest(D/n) for n in ['grade.py','evaluation_rows.json.gz','results.json','paired.json']},
             'all_original_reference_metrics_reproduced':True,'bootstrap':'PCG64 301754 multinomial draws of whole tasks, separately per endpoint and panel, 5000'})
    print('reference tables reproduced; evaluated',[(p,s['patch']['n']) for p,s in summary.items()])
if __name__=='__main__':main()
