"""Package the new registered experiments. External model weights and benchmark images stay in their caches."""
import hashlib
import os
import zipfile
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
OUT=Path(os.environ.get('MEMORY_NEXT_OUTPUT',str(ROOT.parents[1]/'outputs')))
TOP={'write_factor','read_policy','repair','transfer','time_read','map_audit','continuation','abstain','handoff_debt','handoff_policy'}
EXT={'.py','.md','.json','.jsonl','.csv','.txt','.log','.sha256','.gz','.zip','.npz','.patch','.sh','.ps1','.png','.yaml','.toml','.tsv','.diff','.html','.rst','.bib'}
EXCLUDE=('repair/grading/attempts/','repair/grading/receipts/','continuation/grading/attempts/','repair/pipe_check/raw/')

def included(path):
    rel=path.relative_to(ROOT)
    if len(rel.parts)>1 and rel.parts[0] not in TOP:return False
    if '__pycache__' in rel.parts or '.git' in rel.parts:return False
    if rel.as_posix().startswith(EXCLUDE):return False
    if path.name.endswith('.tmp') or '.partial' in path.name:return False
    if rel.parts[0]=='map_audit' and path.name in {'data_runs_train.parquet','data_targets_train.parquet'}:return True
    return path.suffix.lower() in EXT or path.name in {'LICENSE','Dockerfile','Makefile'}

def main():
    seal=json.loads((ROOT/'repair/grading/calibration_and_graded.json').read_text(encoding='utf8'))
    assigned=json.loads((ROOT/'repair/assignments.json').read_text(encoding='utf8'))
    assert len(assigned)==12 and sum(map(len,seal['assignments'].values()))==len(assigned),'complete the grader first'
    for required in ['write_factor/results.json','read_policy/results.json','transfer/results.json','transfer/lite_chronology.json','front.py','repair/report_section.py',
                     'read_policy/report_section.py','time_read/report_section.py','time_read/results.json','transfer/report_section.py','transfer/verify_local.py','verify.py','report.py','README_RU.md',
                     'map_audit/report_section.py','continuation/report_section.py','abstain/report_section.py','write_factor/perm_robustness/results.json',
                     'repair/grading/matched_groups.json','continuation/end_lock.json','continuation/results.json','continuation/grading/official_execution.zip','continuation/grading/seal.json',
                     'handoff_debt/report_section.py','handoff_debt/verify.py','handoff_debt/results.json','handoff_policy/report_section.py','handoff_policy/verify.py',
                     'repair/runtime/reconciled.json','repair/pipe_check/raw.zip','repair/pipe_check/report_section.py','repair/pipe_check/writer/verify.py','repair/pipe_check/writer/results.json','NEXT_STUDY_RU.md']:
        assert (ROOT/required).is_file(),required
    OUT.mkdir(parents=True,exist_ok=True)
    bundle=OUT/'agent-memory-next-records.zip';temp=bundle.with_suffix('.partial.zip')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        hashes=[]
        for source in sorted(ROOT.rglob('*')):
            if source.is_file() and included(source) and source.relative_to(ROOT).as_posix()!='MANIFEST.sha256':
                rel=source.relative_to(ROOT).as_posix()
                data=source.read_bytes()
                z.writestr(rel,data)
                hashes.append(hashlib.sha256(data).hexdigest()+'  '+rel)
        z.writestr('MANIFEST.sha256','\n'.join(hashes)+'\n')
    with zipfile.ZipFile(temp) as z:assert z.testzip() is None
    temp.replace(bundle)
    print(f'{len(hashes)} files, {bundle.stat().st_size} bytes, SHA256 {hashlib.sha256(bundle.read_bytes()).hexdigest()}')

if __name__=='__main__':main()

