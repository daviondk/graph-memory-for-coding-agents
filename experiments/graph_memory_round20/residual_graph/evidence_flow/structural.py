"""Apply the same pair estimator to existing train-only readers without touching model weights."""
from pathlib import Path
import sys
from unittest.mock import patch
import analyze as a

HERE = a.HERE
SRC = a.ROOT.parent / 'typed_reader'
ALGORITHMS = {'dense':SRC/'train_bm25','typed':SRC/'train_bm25','shuffled':SRC/'train_bm25',
              'role_degrees':SRC/'mechanism/test-train'}
DENSE = SRC.parent.parent/'graph_memory_round19/trained_rank'
CONTRASTS = (('role_degrees','dense'),('typed','shuffled'))

def inputs():
    return {arm:a.sha(p/'forecast-seal.json') for arm,p in ALGORITHMS.items()}

def lock():
    assert not (HERE/'structural-plan.json').exists()
    a.put(HERE/'structural-plan.json', dict(inputs=inputs(), dense=a.sha(DENSE/'forecast-seal.json'),
          analyzer=a.sha(HERE/'analyze.py'), source=a.sha(HERE/'structural.py'),
          method=a.sha(HERE/'STRUCTURAL_RU.md'), based_on=a.sha(HERE/'plan.json'), comparisons=CONTRASTS))

def run():
    plan=a.read(HERE/'structural-plan.json')
    assert plan['inputs']==inputs() and plan['source']==a.sha(HERE/'structural.py')
    assert plan['analyzer']==a.sha(HERE/'analyze.py') and plan['method']==a.sha(HERE/'STRUCTURAL_RU.md')
    assert plan['dense']==a.sha(DENSE/'forecast-seal.json')
    primary=a.read(HERE/'plan.json')
    assert primary['gold']==a.sha(a.GOLD)
    gold={q:a.by_field(spans) for q,spans in a.read(a.GOLD).items()}
    event_counts={q:len({event for event,_ in fields}) for q,fields in gold.items()}
    recs={q:{'q':q,'m':m,'k':{}} for q,m in event_counts.items() if m>=2}
    dense_files=a.read(DENSE/'forecast-seal.json')['forecasts']
    for part in range(8):
        name=f'forecasts-main-{part}.json.gz'
        assert a.sha(DENSE/name)==dense_files[name]
        dense={row['q']:row for row in a.read(DENSE/name)}
        fname=f'forecast-{part}.json.gz'
        for base in set(ALGORITHMS.values()):
            assert a.sha(base/fname)==a.read(base/'forecast-seal.json')['forecasts'][fname]
            for row in a.read(base/fname):
                q=row['q']
                if q not in recs:
                    continue
                target=recs[q]
                assert target.setdefault('t',row['t'])==row['t']==dense[q]['t']
                candidates=dense[q]['rr']
                for algorithm,src in ALGORITHMS.items():
                    if src!=base:
                        continue
                    ids=row['selection'][algorithm]['prefix']
                    assert len(ids)==len(set(ids)) and algorithm not in target['k']
                    selected=[candidates[i] for i in ids]
                    assert sum(n['token_count'] for n in selected)<=2048
                    target['k'][algorithm]=a.count_complete(gold[q],selected)
    checks=set()
    for base in set(ALGORITHMS.values()):
        for row in a.read(base/'outcomes.json.gz'):
            q,arm=row['q'],row['arm']
            if q in recs and row['policy']=='prefix' and ALGORITHMS.get(arm)==base:
                r=recs[q]
                assert r['t']==row['t'] and (r['k'][arm]==r['m'])==row['full_support']
                assert (q,arm) not in checks
                checks.add((q,arm))
    assert len(gold)==2000 and len(checks)==len(recs)*len(ALGORITHMS)
    rec_file=HERE/'train_structural-events.json.gz'
    a.put(rec_file,[recs[q] for q in sorted(recs)])
    out=dict(plan=a.sha(HERE/'structural-plan.json'),records=a.sha(rec_file),partitions={})
    with patch.multiple(a, ARMS=tuple(ALGORITHMS), CONTRASTS=CONTRASTS):
        for scope in a.SCOPES:
            sub=[r for r in recs.values() if scope=='minimum_two' or r['m']==2]
            out['partitions'][scope]=a.summarize(sub,primary['seed'],primary['boot'])
    a.put(HERE/'train_structural-results.json',out)
    print(out['partitions']['minimum_two']['contrasts'],flush=True)

if __name__=='__main__':
    {'lock':lock,'score':run}[sys.argv[1]]()
