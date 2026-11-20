"""Independent small offline verifier; no source tasks, model, or network required."""
import csv
import hashlib
import json
from fractions import Fraction
from itertools import combinations
from math import comb
from pathlib import Path
from policy import make_assignment

root=Path(__file__).resolve().parent
load=lambda name:json.loads((root/name).read_text(encoding='utf8'))
receipt=load('result_receipt.json')
for name,h in receipt['files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==h,name
r=load('results.json');assignments=load('assignments.json')
with (root/'per_query.csv').open(encoding='utf8',newline='') as f:
    rows=list(csv.DictReader(f))
assert len(rows)==len(assignments)==99
for row,a in zip(rows,assignments):
    assert int(row['ordinal'])==a['ordinal'] and int(row['gate_full'])==a['full'] and int(row['random_full'])==a['random_full']
    assert row['gate_key']==row[('always' if a['full'] else 'never')+'_key']
    assert row['random_key']==row[('always' if a['random_full'] else 'never')+'_key']
for name in ['gate','never','always','random']:
    assert all(row[name+'_key'] in a['slate'] for row,a in zip(rows,assignments))
    for label in ['any','first','last']:
        expected=sum(row[name+'_instance_id'] in row['gold_'+label].split('|') for row in rows)
        assert expected==r['outcomes'][name][label]
    for src,out in [('input','prompt'),('output','output'),('full','full')]:
        assert sum(int(row[name+'_'+src]) for row in rows)==r['outcomes'][name][out]
n=len(rows);k=sum(a['full'] for a in assignments)
base=sum(int(row['never_any']) for row in rows)
diff=[int(row['always_any'])-int(row['never_any']) for row in rows if row['always_any']!=row['never_any']]
# Exact conditional null by enumerating subsets of discordant observations only.
cnt=0
for g in range(len(diff)+1):
    for subset in combinations(range(len(diff)),g):
        if base+sum(diff[i] for i in subset)>=r['outcomes']['gate']['any']:
            cnt+=comb(n-len(diff),k-g)
assert abs(float(Fraction(cnt,comb(n,k)))-r['uniform']['probability_random_ge_gate'])<1e-15
slate=['A','B','C','D','E']
short={k:set() for k in slate}
q={'ordinal':0,'query':'PATCH uses FooCount'}
assert make_assignment(q,slate,{'foocount':['B']}, short)['full']
short['B']={'foocount'}
assert not make_assignment(q,slate,{'foocount':['B']},short)['full']
short['A']={'foocount'}
assert make_assignment(q,slate,{'foocount':['B']},short)['full']
assert not make_assignment(q,slate,{'foocount':['A','B']},short)['full']
print(f'All {len(receipt["files"])} model/data artifact hashes, {n} branch outcomes in four policies, exact matched null, and four feature canaries verified.')

