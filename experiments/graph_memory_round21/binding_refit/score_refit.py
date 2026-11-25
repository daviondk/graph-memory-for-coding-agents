"""Apply independent coverage implementations to finite, fully sealed forecasts."""
from collections import defaultdict
from pathlib import Path
import sys
from refit import D,R20,ref,sha,read,save,ARMS,INCR,verify_fit
from score_readout import paired
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan
import importlib.util
import numpy as np

spec=importlib.util.spec_from_file_location('independent_r17',D.parents[1]/'graph_memory_round17/isetrace/verify_records.py')
ind=importlib.util.module_from_spec(spec);spec.loader.exec_module(ind)
COMPARE=(('exact/exact','append/append'),('exact/exact','exact/append'),('append/exact','append/append'),('append/append','exact/append'),('dual/both','exact/exact'),('dual/both','append/append'),('dual/both','dual/zero'),('exact/exact','r20/exact'),('r20/exact','r20/append'),('exact/exact','dense'),('append/append','dense'))


def assess(recs):
    summ={}
    for a in ARMS:
        vals=[r['arms'][a] for r in recs]
        summ[a]={k:float(np.mean([v[k] for v in vals])) for k in ('coverage','density','tokens')}
        summ[a]['hits']=sum(v['fs'] for v in vals)
    return dict(q=len(recs),t=len({r['t'] for r in recs}),means=summ,pairs={a+' minus '+b:paired(recs,a,b) for a,b in COMPARE})


def score(extra):
    verify_fit()
    if extra:
        base=R20/'untuned_holdout';fn=base/'dense-ranks-extra80.json.gz';rs=read(fn);rs=rs['rows'] if isinstance(rs,dict) else rs
        assert sha(fn)==read(base/'forecast-seal.json')['ranks']
        pp=D/'forecast-extra.json.gz';assert sha(pp)==read(D/'forecast-extra-lock.json')['forecast']
        refs=[(pp,rs)];truth=read(D.parents[1]/'graph_memory_round19/write_transfer/gold-spans.json.gz')
    else:
        seal=read(D/'forecast-seal.json')
        assert seal['fit']==sha(D/'fit-lock.json')
        refs=[]
        for i in range(8):
            pp=D/f'forecast-{i}.json.gz';assert sha(pp)==seal['shards'][pp.name]
            refs.append((pp,read(ref.TR/f'forecasts-main-{i}.json.gz')))
        truth=read(ref.OFF/'gold-spans.json.gz')
    outcomes=[]
    for pp,rs in refs:
        mapping={r['q']:r for r in rs}
        for z in read(pp):
            q=z['q'];rr=mapping[q]['rr'];gold=truth[q];sp=tuple(SourceSpan.model_validate(p) for p in gold)
            records=[RankedNodeRecord.model_validate(n) for n in rr]
            memo={};arms={}
            for a,ids in z['picks'].items():
                key=tuple(ids)
                if key not in memo:
                    ranked=tuple(records[j] for j in ids);tok=sum(v.token_count for v in ranked)
                    assert len(ids)==len(set(ids)) and tok<=2048
                    m=span_metrics_under_token_budget(ranked,sp,2048)
                    baseline=ind.metrics(gold,[rr[j] for j in ids])
                    assert all(abs(u-getattr(m,k))<1e-12 for u,k in zip(baseline,('coverage','density','full_support'),strict=True))
                    memo[key]=dict(fs=int(m.full_support),tokens=tok,coverage=m.coverage,density=m.density)
                arms[a]=memo[key]
            outcomes.append(dict(q=q,t=z['t'],pilot=z['pilot'],arms=arms,different={a+'/'+b:z['picks'][a]!=z['picks'][b] for a,b in COMPARE}))
    label='extra' if extra else 'test'
    save(D/f'{label}-outcomes.json.gz',outcomes)
    if extra:
        assert len(outcomes)==27 and len({r['t'] for r in outcomes})==21
        results={'novel':assess(outcomes)}
    else:
        subset=[r for r in outcomes if not r['pilot']]
        assert len(subset)==1845 and len({r['t'] for r in subset})==1111
        results={k:assess(v) for k,v in [('primary',subset),('all',outcomes),('pilot',[r for r in outcomes if r['pilot']])]}
    save(D/f'{label}-results.json',results)
    for k,g in results.items():print(k,g['q'],{a:v['hits'] for a,v in g['means'].items()},g['pairs']['exact/exact minus append/append'],flush=True)


if __name__=='__main__':score(sys.argv[1]=='extra')

