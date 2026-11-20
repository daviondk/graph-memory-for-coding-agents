"""Verify every official output, case/condition association and numeric summary offline."""
import hashlib
import json
import zipfile
from pathlib import Path

here=Path(__file__).resolve().parent
def read(p):return json.loads((here/p).read_text(encoding='utf8'))
def sha(blob):return hashlib.sha256(blob).hexdigest()
for name,expected in read('seal.json').items():
    assert sha((here/name).read_bytes())==expected,name
summary=read('summary.json')
flat={(r['instance_id'],r['arm']):r for r in summary['rows']}
assert len(flat)==8 and summary['n_issues']==4 and summary['n_pr']==3
with zipfile.ZipFile(here/'official_execution.zip') as arch:
    assert arch.testzip() is None
    for iid,digest in read('provenance.json')['initial_brief_receipts_sha256'].items():
        blob=arch.read('parents/'+iid+'.json')
        assert sha(blob)==digest
        parent=json.loads(blob)
        assert parent['instance_id']==iid and parent['arm']=='brief'
        for arm in ('last_two','manifest'):
            assert parent['resolved']==flat[iid,arm]['initial_brief_resolved']
    receipts=[n for n in arch.namelist() if n.startswith('receipts/') and n.endswith('.json')]
    assert len(receipts)==8
    for name in receipts:
        r=json.loads(arch.read(name))
        item=flat[r['instance_id'],r['arm']]
        report=arch.read(r['official_summary'])
        assert r['official_report_sha256']==sha(report)
        q=json.loads(report)[r['instance_id']]
        assert q['resolved']==r['resolved']==item['resolved']
        assert r['input_patch_bytes']==item['candidate_bytes']
        run='attempts/'+r['run_id']+'/'
        assert r['console_sha256']==sha(arch.read(run+'official_console.log'))
        for filename,obj in r['test_logs_sha256'].items():
            if filename=='patch.diff':continue
            paths=[n for n in arch.namelist() if n.startswith(run+'logs/') and n.endswith('/'+filename)]
            assert len(paths)==1 and sha(arch.read(paths[0]))==obj['sha256']
for arms in read('provenance.json')['controls'].values():
    assert arms['gold']['resolved'] and not arms['inert']['resolved'] and not arms['empty']['resolved']
    assert arms['gold']['tests_status'] and arms['inert']['tests_status'] and not arms['empty']['tests_status']
print('Verified 8 complete continuation reports, raw logs, and 12 references to calibrated controls.')

