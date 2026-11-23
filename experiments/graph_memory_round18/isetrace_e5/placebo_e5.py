"""Apply the published R18 controls to E5 ranks before reading E5 outcomes."""
from collections import defaultdict
from statistics import mean
import sys
from project import ROOT,OFF,load,put,pilot
import placebo
from verify_records import metrics as independent
M=('coverage','density','full_support','tokens')
def plan():
    put(ROOT/'placebo-plan.json',dict(local={n:pilot.sha(ROOT/n) for n in ('PLACEBO_PROTOCOL_RU.md','placebo_e5.py','plan-seal.json')},
        official={n:pilot.sha(OFF/n) for n in ('placebo.py','placebo-event-metadata.json.gz','placebo-plan.json')}))
def verify():
    p=load(ROOT/'placebo-plan.json')
    for d,section in [(ROOT,'local'),(OFF,'official')]:
        assert all(pilot.sha(d/n)==h for n,h in p[section].items())
def forecasts():
    verify();seal=load(ROOT/'forecast-seal.json');meta=load(OFF/'placebo-event-metadata.json.gz')
    hashes={}
    for i in range(8):
        n=f'forecasts-main-{i}.json.gz';assert pilot.sha(ROOT/n)==seal['forecasts'][n]
        preds={}
        for r in load(ROOT/n):
            t=r['t'];shape,gr,_=placebo.make_groups(r['rr'],meta[t]);order=[v['node_id'] for v in r['rr']];prefix=r['arms']['prefix']
            ix={k:j for j,k in enumerate(order)}
            assert placebo.package(order,prefix,shape,{})==r['arms']['related']
            preds[r['q']]={mode:[[ix[k] for k in placebo.package(order,prefix,shape,placebo.cell_mapping(gr[mode],s,t))[len(prefix):]] for s in placebo.SEEDS] for mode in placebo.CONTROLS}
        name=f'placebo-picks-{i}.json.gz';put(ROOT/name,preds);hashes[name]=pilot.sha(ROOT/name)
    put(ROOT/'placebo-seal.json',dict(official_forecast=pilot.sha(ROOT/'forecast-seal.json'),placebo_plan=pilot.sha(ROOT/'placebo-plan.json'),files=hashes))
def score():
    verify();lock=load(ROOT/'placebo-seal.json');assert all(pilot.sha(ROOT/n)==h for n,h in lock['files'].items())
    assert lock['official_forecast']==pilot.sha(ROOT/'forecast-seal.json')
    gold=load(OFF/'gold-spans.json.gz');out=[];result={}
    for i in range(8):
        preds=load(ROOT/f'placebo-picks-{i}.json.gz')
        for r in load(ROOT/f'forecasts-main-{i}.json.gz'):
            q,t,rr=r['q'],r['t'],r['rr']
            lookup={n['node_id']:j for j,n in enumerate(rr)};base=[lookup[k] for k in r['arms']['prefix']];real=[lookup[k] for k in r['arms']['related']]
            cache={}
            def score1(jj):
                key=tuple(jj)
                if key not in cache:
                    nodes=[rr[j] for j in jj];vals=independent(gold[q],nodes);cost=sum(n['token_count'] for n in nodes);assert cost<=2048
                    cache[key]=dict(zip(M,(*vals,cost),strict=True))
                return cache[key]
            actual=score1(real)
            for mode,allp in preds[q].items():
                values=[score1(base+sub) for sub in allp]
                out.append(dict(q=q,t=t,mode=mode,actual=actual,placebo={m:mean(v[m] for v in values) for m in M},
                                seeds_fs=[v['full_support'] for v in values],changed_fraction=mean(set(base+s)!=set(real) for s in allp)))
    for mode in placebo.CONTROLS:
        rr=[r for r in out if r['mode']==mode];assert len(rr)==len(gold)
        result[mode]=dict(n=len(rr),changed_fraction=mean(r['changed_fraction'] for r in rr),true_mean={m:mean(r['actual'][m] for r in rr) for m in M},
                        shuffled_mean={m:mean(r['placebo'][m] for r in rr) for m in M},diff_fs_boot95=placebo.cluster_ci([(r['t'],r['actual']['full_support']-r['placebo']['full_support']) for r in rr]),
                        seed_fs=[mean(r['seeds_fs'][s] for r in rr) for s in placebo.SEEDS])
    put(ROOT/'placebo-outcomes.json.gz',out);put(ROOT/'placebo-results.json',result)
if __name__=='__main__':{'plan':plan,'predict':forecasts,'score':score}[sys.argv[1]]()
