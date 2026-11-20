"""Offline, independent validation of digests, calibration and outcome ledger."""
import hashlib
import json
import zipfile
from pathlib import Path

here=Path(__file__).resolve().parent
read=lambda n:json.loads((here/n).read_text(encoding='utf8'))
hashb=lambda data:hashlib.sha256(data).hexdigest()
for name,expected in read('seal.json').items():
    assert hashb((here/name).read_bytes())==expected,name
valid=read('calibration_and_graded.json'); flat=read('summary.json')
with zipfile.ZipFile(here/'official_execution.zip') as z:
    assert z.testzip() is None
    outcomes={}
    for name in z.namelist():
        if not name.startswith('receipts/') or not name.endswith('.json'):continue
        r=json.loads(z.read(name))
        summary=z.read(r['official_summary'])
        assert hashb(summary)==r['official_report_sha256']
        q=json.loads(summary)[r['instance_id']]
        assert q['resolved']==r['resolved']
        prefix='attempts/'+r['run_id']+'/'
        assert hashb(z.read(prefix+'official_console.log'))==r['console_sha256']
        for ln,info in r['test_logs_sha256'].items():
            if ln=='patch.diff':continue
            candidates=[f for f in z.namelist() if f.startswith(prefix+'logs/') and f.endswith('/'+ln)]
            assert len(candidates)==1 and hashb(z.read(candidates[0]))==info['sha256'],ln
        arm=r['arm'];iid=r['instance_id'];assert (iid,arm) not in outcomes;outcomes[(iid,arm)]=q['resolved']
        assert flat['calibration' if arm in ('empty','gold','inert') else 'arms'][arm]['per_target'][iid]==q['resolved']
    assert len(outcomes)==flat['coverage']
    for iid in valid['targets']:
        assert outcomes[(iid,'gold')] and not outcomes[(iid,'inert')] and not outcomes[(iid,'empty')]
    nreal=sum(a not in ('empty','gold','inert') for _,a in outcomes)
    assert nreal==sum(len(q) for q in valid['assignments'].values())
print('Verified',len(outcomes),'independent official trial/control reports;',nreal,'real submissions.')

