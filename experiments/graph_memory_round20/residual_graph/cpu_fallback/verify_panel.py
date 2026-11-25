"""Standalone verification locates sibling releases for coordinate arithmetic and official labels."""
from pathlib import Path
import importlib.util,sys,shutil,hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
import arithmetic as v
def verify(name):
    sub=HERE/name;seal=v.get(sub/'forecast-seal.json')
    assert all(v.sha(sub/k)==h for k,h in seal['files'].items())
    assert v.sha(sub/'prediction-plan.json')==seal['plan'] and v.sha(sub/'best.pt')==v.get(sub/'checkpoint.json')['sha']
    outcomes={(r['stage'],r['method'],r['arm'],r['q']):r for r in v.get(sub/'outcomes.json.gz')}
    reports=v.get(sub/'results.json');calls=v.get(HERE/'inputs/test-call-map.json.gz');devcalls=v.get(HERE/'dev-call-map.json.gz');got=set();cohort=v.get(HERE/'cohorts.json')[name]
    assert set(cohort['q'])=={r['task_id'] for r in v.get(sub/'train-pairs.json.gz')}
    for stage in ('dev','test'):
        gp=HERE/'inputs'/f'{stage}-gold.json.gz'
        gold={q:v.merged(g) for q,g in v.get(gp).items()};panel_queries=set()
        for method in ('rgcn','seed'):
            files=sorted(sub.glob(f'forecasts-{method}-*.json.gz')) if stage=='test' else [sub/f'dev500-pu-{method}-ranks.json.gz']
            for f in files:
                for r in v.get(f):
                    q,t=r['q'],r['t'];order=[n['node_id'] for n in r['rr']];pool={n['node_id']:n for n in r['rr']};panel_queries.add(q)
                    assert set(order)==set(pool) and order==sorted(order,key=lambda k:(-pool[k]['score'],k))
                    for arm,S in r['arms'].items():
                        key=stage,method,arm,q;assert key not in got;got.add(key)
                        assert v.pack(order,pool,(calls if stage=='test' else devcalls)[t],arm)==S
                        read=[pool[k] for k in S];metric=v.metric(gold[q],read);assert metric['tokens']<=2048
                        v.check(metric,outcomes[key])
        assert len(panel_queries)==(2000 if stage=='test' else 500)
        for k,value in reports[stage]['metrics'].items():
            a,b=k.split('/');assert sum(x['full_support'] for (st,m,arm,_),x in outcomes.items() if st==stage and m==a and arm==b)==value['hits']
    assert got==set(outcomes) and len(got)==15000
    print(name,'15000 matched measurements verified')
if __name__=='__main__':verify(sys.argv[1])

