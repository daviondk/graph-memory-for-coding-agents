"""Validate the registered inputs, native return codes, responses, and all five confusion matrices."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import zipfile

here=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda n:json.loads((here/n).read_text(encoding='utf8'))
reg=read('design_lock.json');end=read('calls_lock.json')
for name,digest in read('seal.json').items():assert sha((here/name).read_bytes())==digest,name
for name,digest in reg['files'].items():assert sha((here/name).read_bytes())==digest,name
assert sha((here/'input_audit_seal.json').read_bytes())==reg['input_audit_seal']
assert sha((here.parent/'raw.zip').read_bytes())==reg['input_raw_archive_sha256']
assert sha((here.parent/'results.json').read_bytes())==reg['input_results_sha256']
assert sha((here/'model_calls.jsonl').read_bytes())==end['model_calls_sha256']
assert sha((here/'design_lock.json').read_bytes())==end['registration_sha256']
payloads=read('payloads.json');jobs=read('schedule.json');r=read('results.json')
ledger=list(map(json.loads,(here/'model_calls.jsonl').read_text(encoding='utf8').splitlines()))
by={x['key']:x for x in ledger}
assert len(ledger)==len(by)==len({x['response_id'] for x in ledger})==40
assert [j['key'] for j in jobs]==[j['key'] for j in ledger]
assert Counter(j['arm'] for j in jobs[::2])=={'hidden':10,'measured':10}
assert all(reg['utc']<row['start']<=row['end']<=end['utc'] for row in ledger)
for q in ledger:
    assert q['payload_sha256']==sha(json.dumps(payloads[q['key']],ensure_ascii=False).encode())
classes='ABCDE';decisions={x:{} for x in r['methods']};truth={}
with zipfile.ZipFile(here.parent/'raw.zip') as z:
    for i in range(1,21):
        a=payloads[f'{i:02d}_hidden'];b=payloads[f'{i:02d}_measured']
        assert {k:v for k,v in a.items() if k!='messages'}=={k:v for k,v in b.items() if k!='messages'}
        assert a['messages'][0]==b['messages'][0]
        ad=json.loads(a['messages'][1]['content']);bd=json.loads(b['messages'][1]['content'])
        hidden=ad.pop('pytest_invocations_in_order');measured=bd.pop('pytest_invocations_in_order')
        assert ad==bd and len(hidden)==len(measured)
        assert all(v=={'native_rc':'unknown','collect_only':'unknown'} for v in hidden)
        base='raw/%02d/'%i
        design=json.loads(z.read(base+'design.json'))
        assert ad['command']==design['command']
        status=[int(s) for s in z.read(base+'instrumented/pytest.tsv').splitlines()]
        assert [v['native_rc'] for v in measured]==status
        mode=[p['collect_only'] for p in design['pipelines']]
        assert [v['collect_only'] for v in measured]==mode
        expected='A' if 1 in status else 'B' if any(k in (2,3,4,5,6) for k in status) else 'D' if all(mode) else 'C'
        truth[i]=expected
        decisions['always_fail'][i]='A';decisions['regex'][i]='A' if design['failure_evidence'] else 'E';decisions['decoder'][i]=expected
        for arm in ('hidden','measured'):
            content=by[f'{i:02d}_{arm}']['raw'].strip()
            decisions[arm][i]=content if re.fullmatch('[ABCDE]',content) else '!'
for key,v in decisions.items():
    cm={x:{y:0 for y in classes+'!'} for x in classes}
    for i,out in v.items():cm[truth[i]][out]+=1
    metric=r['methods'][key]
    assert cm==metric['confusion'] and sum(cm[x][x] for x in classes)==metric['correct']
    assert sum(out in 'ABCD' for out in v.values())==metric['claims']
    assert sum(out=='C' and truth[i]!='C' for i,out in v.items())==metric['false_passed']
assert Counter(truth.values())==r['classes']
w=sum(decisions['measured'][i]==truth[i] and decisions['hidden'][i]!=truth[i] for i in truth)
l=sum(decisions['hidden'][i]==truth[i] and decisions['measured'][i]!=truth[i] for i in truth)
assert (w,l,20-w-l)==tuple(r['paired'][f] for f in ('wins','losses','ties'))
for arm,amounts in r['usage'].items():
    assert all(v==sum(x['usage'][k] for x in ledger if x['arm']==arm) for k,v in amounts.items())
print('Verified 40 distinct local completions, 40 frozen prompts, 21 exit codes, five confusion matrices, and 20 pairs.')

