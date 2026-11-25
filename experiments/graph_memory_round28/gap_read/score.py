"""Score signed choices and compare paired trajectories with physical cost diagnostics."""
from store import *
from collections import Counter
from statistics import mean
import numpy as np
import importlib.util
spec=importlib.util.spec_from_file_location('r25_annotations',R25/'analyse.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
def select_metrics(known,op,gold):
    visible=old.spans(known);returned=old.spans([v[:3] for v in op]);joint=old.spans(visible+returned)
    cov=max(old.overlap(joint,g)/old.length(g) for g in gold)
    twice=old.overlap(returned,visible);n=old.length(returned)
    return {'full':int(cov==1),'coverage':cov,'tokens':sum(v[3] for v in op),'requests':len(op),'already':twice,'output_chars':n,'repeat_fraction':twice/n if n else 0.,'empty':int(n==0)}
def agg(entries):
    met={k:mean(e[k] for e in entries) for k in entries[0]}
    met['hits']=sum(e['full'] for e in entries);met['repeat_pooled']=sum(e['already'] for e in entries)/max(1,sum(e['output_chars'] for e in entries));return met
def infer(rows,a,mode):
    keys=('full','coverage','tokens','requests','repeat_fraction')
    query={};group=defaultdict(list)
    for r in rows:
        x,y=r['eq'][a] if mode=='equal' else [r['arms']['gap'],r['arms'][a]]
        diff=np.array([x[k]-y[k] for k in keys]);query[r['q']]=diff;group[r['t']].append(diff)
    order=sorted(group);n=np.array([len(group[g]) for g in order]);m=np.array([np.sum(group[g],axis=0) for g in order])
    rng=np.random.default_rng(263117);draw=[]
    for _ in range(200):
        ix=rng.integers(len(n),size=(100,len(n)));draw.append(m[ix].sum(axis=1)/n[ix].sum(axis=1)[:,None])
    ci=np.quantile(np.concatenate(draw),[.025,.975],axis=0);d=m.sum(axis=0)/n.sum()
    votes=m[:,0].astype(int);w=votes[votes!=0];obs=abs(sum(w))
    if len(w)<=20:
        cnt=Counter({0:1})
        for v in w:
            new=Counter()
            for t,k in cnt.items():new[t+int(v)]+=k;new[t-int(v)]+=k
            cnt=new
        p=sum(c for t,c in cnt.items() if abs(t)>=obs)/2**len(w);method='exact'
    else:
        ex=0
        for _ in range(200):
            a_sign=rng.choice([-1,1],size=(500,len(w)));ex+=int((abs(a_sign@w)>=obs).sum())
        p=(1+ex)/100001;method='monte_carlo_plus_one'
    return {'metrics':{k:{'delta':float(d[i]),'ci95':ci[:,i].tolist()} for i,k in enumerate(keys)},'wins':sum(int(x[0]>0) for x in query.values()),'losses':sum(int(x[0]<0) for x in query.values()),'p':p,'inference':method,'clusters':len(n),'queries':int(n.sum())}
def score(name):
    seal=read(D/f'{name}-seal.json');f=D/f'{name}-forecasts.json.gz';assert sha(f)==seal['rows'] and sha(D/'analysis-lock.json')==seal['analysis_plan']
    picks=read(R25/f'{name}-choices.json.gz');allp=read(f);raw=old.targets(name,picks)
    rows=[]
    for q,r in sorted(picks.items()):
        g=[old.spans(v) for v in raw[q]];pred=allp[q]
        m=lambda o:select_metrics(r['base'],o,g)
        arms={a:m(o) for a,o in pred['arms'].items()};eq={a:[m(o) for o in pair] for a,pair in pred['eq'].items()}
        assert all(u['tokens']==v['tokens'] for u,v in eq.values()) and all(v['tokens']<=256 for v in arms.values()) and all(arms[a]['already']==0 for a in ('gap','window'))
        rows.append({'q':q,'t':r['t'],'initial':m([])['full'],'arms':arms,'eq':eq,'diag':pred['diag']})
    base=read(R25/f'{name}-results.json')
    assert sum(r['arms']['both']['full'] for r in rows)==base['methods']['both']['fs']
    ok=[r for r in rows if not r['initial']]
    obj={'n':len(rows),'groups':len({r['t'] for r in rows}),'initial':sum(r['initial'] for r in rows),'online':{a:agg([r['arms'][a] for r in rows]) for a in rows[0]['arms']},
         'equal':{a:[agg([r['eq'][a][i] for r in rows]) for i in (0,1)] for a in ('window','both')},
         'paired':{a+'-'+m:infer(rows,a,m) for a in ('window','both') for m in ('equal','online')},'initial_misses':len(ok),
         'misses_primary':infer(ok,'window','equal'),'no_component':sum(r['diag']['no_component'] for r in rows),
         'single_structural_unit':sum(r['diag'].get('field_units')==1 for r in rows),'same_candidate_pools':sum(r['diag'].get('same_span_pools',False) for r in rows)}
    obj['per_query']=save(D/f'{name}-outcomes.json.gz',rows);obj['forecast']=sha(D/f'{name}-seal.json');obj['score']=sha(Path(__file__));save(D/f'{name}-results.json',obj)
    print(name,obj['n'],obj['online']['gap']['hits'],obj['online']['window']['hits'],obj['paired']['window-equal']['metrics']['full'])
if __name__=='__main__':score(sys.argv[1])
