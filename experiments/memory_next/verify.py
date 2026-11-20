"""Check a freshly extracted ZIP on CPU without network access or model weights."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
J=lambda p:json.loads(p.read_text(encoding='utf8'))
sha=lambda b:hashlib.sha256(b).hexdigest()


def thresholds():
    expected=set()
    for line in (ROOT/'MANIFEST.sha256').read_text(encoding='utf8').splitlines():
        h,name=line.split('  ',1)
        assert name not in expected,name
        expected.add(name)
        assert sha((ROOT/name).read_bytes())==h,name
    actual={f.relative_to(ROOT).as_posix() for f in ROOT.rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    assert actual==expected|{'MANIFEST.sha256'}, sorted(actual.symmetric_difference(expected|{'MANIFEST.sha256'}))
    for sub,script in [('write_factor','verify.py'),('read_policy','verify.py'),('transfer','verify_local.py'),('repair/grading','verify_archive.py'),('.','verify_time_read.py'),('map_audit','verify.py'),('abstain','verify.py'),('continuation','verify.py'),('continuation/grading','verify.py'),('handoff_debt','verify.py'),('handoff_policy','verify.py'),('repair/runtime','verify.py'),('repair/pipe_check','verify.py'),('repair/pipe_check/writer','verify.py')]:
        path=ROOT/sub/script
        subprocess.run([sys.executable,'-B',str(path)],cwd=path.parent,check=True)
    for label in ('score.py','within_export.py'):
        path=ROOT/'write_factor/perm_robustness'/label
        subprocess.run([sys.executable,'-B',str(path),'--verify'],cwd=path.parent,check=True)


def solver():
    p=ROOT/'repair';g=p/'grading'
    for name,h in J(p/'solver-freeze.json').items():
        assert sha((p/name).read_bytes())==h,name
    for freeze in ['freeze.json','freeze_v2.json']:
        t=p/'temporal_input'
        for name,h in J(t/freeze)['files'].items():assert sha((t/name).read_bytes())==h
    for name,h in J(g/'seal.json').items():assert sha((g/name).read_bytes())==h,name
    rows=J(p/'assignments.json')
    assert len(rows)==12==len(set(map(tuple,rows)))
    grades=J(g/'calibration_and_graded.json')
    assert len(grades['targets'])==4
    decisions={}
    for arm,entry in grades['assignments'].items():
        for r in entry:
            decisions[(r['instance_id'],arm)]=r
    assert set(decisions)==set(map(tuple,rows))
    allids=set()
    with zipfile.ZipFile(g/'official_execution.zip') as z:
        assert z.testzip() is None
        recs={};controls={}
        for name in z.namelist():
            if not name.startswith('receipts/') or not name.endswith('.json'):continue
            r=json.loads(z.read(name))
            assert sha(z.read(r['official_summary']))==r['official_report_sha256']
            k=(r['instance_id'],r['arm'])
            assert k not in recs
            recs[k]=r
            if r['arm'] in ['gold','empty','inert']:controls[k]=r['resolved']
        for iid,arm in rows:
            stage=p/'runs'/iid/arm
            r=J(stage/'complete.json');graded=decisions[(iid,arm)]
            assert r['id']==iid and r['arm']==arm
            payload=(stage/'candidate.patch').read_bytes()
            assert sha(payload)==r['patch_sha256']==recs[iid,arm]['input_patch_sha256']
            assert recs[iid,arm]['resolved']==graded['resolved']
            inp=out=0
            for index in range(1,r['calls']+1):
                a=J(stage/f'response-{index:02d}.json')
                assert a['id'] not in allids
                allids.add(a['id'])
                inp+=a['usage']['prompt_tokens'];out+=a['usage']['completion_tokens']
                assert (stage/f'prompt-{index:02d}.json').is_file()
            assert (inp,out)==(r['input_tokens'],r['output_tokens'])
        assert len(controls)==12
    safe=J(p/'safe_cards.json');sources={r['id']:r for r in J(p/'temporal_input/selected.json')}
    for iid,arm in rows:
        result=J(p/'runs'/iid/arm/'complete.json')
        assert result['record_available']==bool(safe[iid])==bool(sources[iid]['source_key'])
        assert result['record_key']==sources[iid]['source_key']
    print('12 complete agent assignments, individual patch hashes and grader outcomes, all model token counters and 12 calibration controls verified.')

if __name__=='__main__':
    thresholds()
    solver()
    print('Research archive verified.')

