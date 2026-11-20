"""Regenerate all aggregate results from per-target stratum and outcome records."""
from pathlib import Path
import csv
import json
import hashlib
from collections import Counter
ROOT = Path(__file__).resolve().parent
ARMS = ['no_memory','raw','adp','memory']

def data(n):
    return json.loads((ROOT/n).read_text(encoding='utf8'))

def aggregate(strata, rows):
    eligible = {s['target_id']:s for s in strata if s['valid_target'] and not s['excluded']}
    keyed = {(r['target_id'],r['artifact_condition']):r for r in rows}
    assert len(keyed)==len(eligible)*len(ARMS)==len(rows)
    assert set(keyed)=={(k,m) for k in eligible for m in ARMS}
    out={}
    for name in ['all','past','later','same_fix','unknown']:
        ids=[k for k,x in eligible.items() if name=='all' or x['stratum']==name]
        result = {'n':len(ids),'unique_pr':len({eligible[k]['target_pr_url'] for k in ids}), 'arms':{}}
        for m in ARMS:
            pairs = [(keyed[k,'no_memory']['resolved'],keyed[k,m]['resolved']) for k in ids]
            result['arms'][m]={'solved':sum(b for a,b in pairs),'wins':sum(b and not a for a,b in pairs),
                               'losses':sum(a and not b for a,b in pairs),'nonempty':sum(keyed[k,m]['non_empty_patch'] for k in ids)}
        out[name]=result
    with (ROOT/'tables_aggregate_outcomes.csv').open(encoding='utf8') as f:
        for x in csv.DictReader(f):
            z=out['all']['arms'][x['artifact_condition']]
            assert (z['solved'],z['nonempty'])==(int(x['resolved']),int(x['non_empty_patches']))
    return out

def verify():
    for n,h in data('lock.json').items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    assert aggregate(data('strata.json'),data('outcomes.json'))==data('results.json')
    print('Verified independent archive: 380 outcomes, four published aggregate controls.')
if __name__=='__main__':verify()

