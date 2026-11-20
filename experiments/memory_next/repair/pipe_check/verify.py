"""Verify the published archive without Docker, private tests, or local source checkouts."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import zipfile
here=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda n:json.loads((here/n).read_text(encoding='utf8'))
for n,h in read('seal.json').items():assert sha((here/n).read_bytes())==h,n
lock=read('registration.json')
for n,key in [('PROTOCOL.md','protocol'),('run.py','replay')]:assert lock['files'][key]==sha((here/n).read_bytes())
out=read('results.json')
pattern=re.compile(r'^\s*(?:FAILED\s+\S+::\S+|ERROR\s+(?:\S+::\S+|at setup|collecting)|.*\b[1-9]\d* (?:failed|errors?)\b(?:[,\s]|$).*)',re.I)
cohort=out['commands'];pipes=out['pipelines']
rcs=[];seen=[];cm=Counter();visible_orig=0;false_outer=0;combos=Counter()
with zipfile.ZipFile(here/'raw.zip') as z:
    assert z.testzip() is None
    for r in cohort:
        root='raw/%02d/'%r['command']; design=json.loads(z.read(root+'design.json'))
        assert design['id']==r['issue'] and design['arm']==r['arm'] and design['turn']==r['turn']
        assert r['old_regex']==bool(design['failure_evidence'])
        if design['outer_status']=='Exit 0':visible_orig+=bool(design['failure_evidence'])
        hooked=None
        for mode in ('untouched','instrumented'):
            base=root+mode+'/'
            run=json.loads(z.read(base+'run.json'))
            assert run['utc_begin']>lock['utc']
            seen.append(run['cid'])
            stdout=z.read(base+'stdout.bin');stderr=z.read(base+'stderr.bin')
            assert run['stdout_sha256']==sha(stdout) and run['stderr_sha256']==sha(stderr)
            triggered=any(pattern.search(l) for l in (stdout+b'\n'+stderr).decode('utf8','replace').splitlines())
            if mode=='instrumented':
                assert triggered==r['hooked_regex'];hooked=triggered
            else:assert triggered==r['untouched_regex']
            assert run['native_shell_returncode']==r['hooked_outer' if mode=='instrumented' else 'untouched_outer']
        inner=[int(x) for x in z.read(root+'instrumented/pytest.tsv').splitlines()]
        all_status=z.read(root+'instrumented/pipeline.tsv').decode().splitlines()
        assert len(inner)==len(all_status)==len(design['pipelines'])
        for native,line,desc in zip(inner,all_status,design['pipelines']):
            segment,outer,status=line.split('\t')
            codes=list(map(int,status.split()))
            assert native==codes[0] and codes[-1]==int(outer) and len(codes)==len(desc['stages'])
            assert int(segment)==desc['segment']
            combos.update(zip(desc['stages'],codes))
        assert inner==r['pytest_rcs'];rcs.extend(inner)
        negative=any(inner);cm[bool(hooked),negative]+=1
        false_outer+=int(r['hooked_outer']==0 and negative)
assert len(seen)==len(set(seen))==40
assert len(cohort)==out['n_commands']==20 and len(rcs)==len(pipes)==out['n_pipeline']==21
assert sum(r['verified'] for r in cohort)==out['verified']==20
assert sum(r['hooked_outer']==0 for r in cohort)==out['zero_outer_n']==20 and false_outer==out['zero_outer_nonzero_native']==18
assert dict(Counter(rcs))=={int(k):v for k,v in out['native_counts'].items()}
assert visible_orig==out['original_zero_visible_failure']==11
assert combos['grep',1]==out['grep_no_match']==0 and combos['grep',141]==out['sigpipe_compatible']==5
assert cm[True,True]==11 and cm[True,False]==0 and cm[False,True]==7 and cm[False,False]==2
assert len(list(csv.DictReader((here/'commands.csv').open(encoding='utf8'))))==20
assert len(list(csv.DictReader((here/'pipelines.csv').open(encoding='utf8'))))==21
print('Verified 40 distinct fresh containers, 20 original commands and all 21 native pytest exit codes.')

