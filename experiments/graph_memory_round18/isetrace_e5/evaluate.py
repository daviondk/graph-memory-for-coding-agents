"""Only run once every source-only forecast is sealed; score with native and independent interval implementations."""
import collections,dataclasses,gzip,json,sys
from statistics import mean
import numpy as np
from project import ROOT,OFF,load,put,pilot,split
from verify_records import metrics as independent
def groups(arr):
    ret=collections.defaultdict(dict)
    for r in arr:
        assert r['q'] not in ret[r['arm']]
        ret[r['arm']][r['q']]=r
    return ret
def compare(test,ref):
    q=sorted(test);assert set(q)==set(ref) and all(test[k]['t']==ref[k]['t'] for k in q)
    g=collections.defaultdict(list);ms=['full_support','coverage','density','f1','tokens']
    for k in q:g[test[k]['t']].append([test[k][m]-ref[k][m] for m in ms])
    keys=sorted(g);sums=np.array([np.sum(g[k],axis=0) for k in keys]);sizes=np.array([len(g[k]) for k in keys])
    rs=np.random.default_rng(13);draw=[]
    for _ in range(40):
        ix=rs.integers(len(keys),size=(250,len(keys)))
        draw.append(sums[ix].sum(axis=1)/sizes[ix].sum(axis=1)[:,None])
    ci=np.quantile(np.concatenate(draw),[.025,.975],axis=0)
    delta=sums.sum(axis=0)/len(q)
    w=sum(test[k]['full_support']>ref[k]['full_support'] for k in q);l=sum(test[k]['full_support']<ref[k]['full_support'] for k in q)
    return dict(n=len(q),trajectories=len(keys),fs_wins=w,fs_losses=l,fs_ties=len(q)-w-l,
                differences={m:dict(estimate=float(delta[j]),cluster_ci95=ci[:,j].tolist()) for j,m in enumerate(ms)})
def evaluate():
    seal=load(ROOT/'forecast-seal.json');assert seal['plan']==pilot.sha(ROOT/'plan-seal.json')
    assert all(pilot.sha(ROOT/n)==h for n,h in seal['forecasts'].items())
    ids=split();goldp=OFF/'gold-spans.json.gz';truth=load(goldp)
    assert set(ids)==set(truth)
    bmfile=OFF/'outcomes.json.gz'
    bm=groups([r for r in load(bmfile) if r['view']=='provenance'])
    out=[];obs=collections.defaultdict(list)
    for filename in sorted(seal['forecasts']):
        group='main' if '-main-' in filename else 'audit-fp32'
        for rec in load(ROOT/filename):
            q=rec['q'];assert rec['t']==ids[q]
            rr=tuple(pilot.RankedNodeRecord.model_validate(r) for r in rec['rr'])
            gold=tuple(pilot.SourceSpan.model_validate(s) for s in truth[q])
            lookup={n.node_id:n for n in rr}
            if rec['partial']:
                n=pilot.RankedNodeRecord.model_validate(rec['partial']);assert n.node_id not in lookup;lookup[n.node_id]=n
            for arm,chosen in rec['arms'].items():
                sub=tuple(lookup[k] for k in chosen);cost=sum(n.token_count for n in sub)
                assert cost<=2048 and len(sub)==len(set(chosen))
                m=pilot.span_metrics_under_token_budget(sub,gold,2048);ind=independent(truth[q],[n.model_dump() for n in sub])
                assert all(abs(a-getattr(m,b))<1e-12 for a,b in zip(ind,('coverage','density','full_support'),strict=True))
                if arm=='prefix':assert m==pilot.span_metrics_under_token_budget(rr,gold,2048)
                row=dict(q=q,t=rec['t'],group=group,arm=arm,tokens=cost,nodes=len(sub),**dataclasses.asdict(m))
                out.append(row);obs[group].append(row)
    result=dict(n_query=len(ids),n_trajectories=len(set(ids.values())),gold_sha256=pilot.sha(goldp),bm25_outcomes_sha256=pilot.sha(bmfile),groups={},paired={})
    for group,rows in obs.items():
        cells=groups(rows)
        ag={a:{m:mean(r[m] for r in rs.values()) for m in ('full_support','coverage','density','f1','tokens','nodes')}|dict(n=len(rs),fs_hits=int(sum(r['full_support'] for r in rs.values()))) for a,rs in cells.items()}
        result['groups'][group]=ag
        for a,b in [('related','prefix'),('related','skip'),('related','value'),('related','clip'),('skip','prefix'),('value','prefix'),('clip','prefix')]:
            result['paired'][group+'/'+a+'-'+b]=compare(cells[a],cells[b])
        for a in ('prefix','related'):
            baseline={q:bm[a][q] for q in cells[a]}
            result['paired'][group+'/'+a+'-bm25_'+a]=compare(cells[a],baseline)
    a=result['groups']['main']['prefix'];assert a['n']==len(ids)
    result['published_prefix']={'full_support_percent':50.50,'coverage_percent':58.20,'observed_fs_percent':100*a['full_support'],'observed_cov_percent':100*a['coverage'],
                               'match_at_published_precision':round(100*a['full_support'],2)==50.50 and round(100*a['coverage'],2)==58.20}
    put(ROOT/'outcomes.json.gz',out)
    put(ROOT/'results.json',result)
    print(result['groups'],flush=True)
if __name__=='__main__':evaluate()
