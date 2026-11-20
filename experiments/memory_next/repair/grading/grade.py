"""Invoke pinned, unmodified SWE-ContextBench runner in Linux/WSL on separate containers."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
UPSTREAM=ROOT/'upstream'
DATA=Path(os.environ.get('SWE_CONTEXT_DATA','/mnt/d/CodexResearch/x20-swe-context'))
TARGETS=('psf__requests-2344','psf__requests-3359','psf__requests-3481','pallets__flask-4039')
ARMS=('brief','eager','on_demand')
INERT=(
    'diff --git a/.memory-grader-inert b/.memory-grader-inert\n'
    'new file mode 100644\n'
    '--- /dev/null\n'
    '+++ b/.memory-grader-inert\n'
    '@@ -0,0 +1 @@\n'
    '+control\n'
)


def read(p):
    return json.loads(p.read_text(encoding='utf8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p,value):
    tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=1)+'\n',encoding='utf8')
    tmp.replace(p)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def command(*args):
    return subprocess.check_output(args,text=True,encoding='utf8',stderr=subprocess.PIPE).strip()


def manifest():
    pin=read(HERE/'upstream_pin.json')
    for rel,h in pin['files'].items():
        assert sha(UPSTREAM/rel)==h,rel
    out=[]
    for iid in TARGETS:
        path=DATA/'case_metadata'/(iid+'.json')
        row=read(path);assert row['instance_id']==iid
        tag='jiayuanz3/swecontextbench:'+iid.replace('__','.')
        image=json.loads(command('docker','image','inspect',tag))[0]
        head,tree=command('docker','run','--rm','--network','none',tag,'bash','-c','cd /testbed && git rev-parse HEAD && git rev-parse HEAD^{tree}').splitlines()
        assert head==row['base_commit']
        out.append({'instance_id':iid,'tag':tag,'image_id':image['Id'],'digests':image['RepoDigests'],
                    'base_commit':head,'tree':tree,'case_file_sha256':sha(path)})
    result={'commit':pin['commit'],'module_sha256':pin['files']['swebench_memory/harness/run_evaluation.py'],'targets':out}
    f=HERE/'image_manifest.json'
    if f.exists():assert read(f)==result
    else:save(f,result)


def grade(iid,arm):
    assert iid in TARGETS and arm in (*ARMS,'empty','inert','gold')
    path=DATA/'case_metadata'/(iid+'.json')
    source=read(path)
    source_hash=sha(path)
    record=next(x for x in read(HERE/'image_manifest.json')['targets'] if x['instance_id']==iid)
    assert source_hash==record['case_file_sha256']
    default_patch={'empty':'','inert':INERT,'gold':source['patch']}
    if arm in default_patch:
        raw=default_patch[arm].encode('utf8')
    else:
        candidate=ROOT/'runs'/iid/arm/'candidate.patch'
        completed=candidate.parent/'complete.json'
        if not candidate.is_file() or not completed.is_file():return False
        raw=candidate.read_bytes()
        solver=read(completed)
        assert len(raw)==solver['patch_bytes'] and hashlib.sha256(raw).hexdigest()==solver['patch_sha256']
    patch=raw.decode('utf8')
    hash_patch=hashlib.sha256(raw).hexdigest()
    receipt_file=HERE/'receipts'/iid/(arm+'.json')
    if receipt_file.exists():
        old=read(receipt_file)
        assert old['input_patch_sha256']==hash_patch and old['official_report_sha256']==sha(HERE/old['official_summary'])
        return True
    run_id='mem26_'+arm+'_'+iid.replace('__','_').replace('-','_')+'_'+uuid.uuid4().hex[:12]
    work=HERE/'attempts'/run_id
    work.mkdir(parents=True,exist_ok=False)
    outfile=work/'prediction.json'
    save(outfile,[{'instance_id':iid,'model_name_or_path':'control' if arm in default_patch else 'qwen38','model_patch':patch}])
    argv=[sys.executable,'-m','swebench_memory.harness.run_evaluation','--dataset_name',str(path),'--predictions_path',str(outfile),
          '--run_id',run_id,'--no-remove-instance-image']
    env={**os.environ,'PYTHONPATH':str(UPSTREAM),'PYTHONIOENCODING':'utf8','PYTHONUNBUFFERED':'1','DOCKER_HOST':'unix:///var/run/docker.sock'}
    start=time.monotonic();utc=stamp()
    with (work/'official_console.log').open('wb') as stream:
        status=subprocess.run(argv,cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT).returncode
    report=work/(run_id+'.json')
    if not report.exists() or status!=0:
        save(work/'infrastructure_error.json',{'utc':utc,'exit':status,'summary_exists':report.exists()})
        raise RuntimeError('Official runner failed; see isolated console at '+str(work))
    j=read(report);assert j['total_instances']==j['submitted_instances']==j['completed_instances']==1
    row=j[iid];logs=next((work/'logs'/'run_evaluation'/run_id).glob('*/'+iid))
    tests=row.get('tests_status',{})
    by={k:{a:len(v[a]) for a in ('success','failure')} for k,v in tests.items()}
    pair_logs={f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in logs.iterdir() if f.is_file()}
    tests_file=logs/'test_output.txt'
    data=tests_file.read_text(encoding='utf8',errors='replace') if tests_file.is_file() else ''
    counts={k:len(v if isinstance(v,list) else json.loads(v)) for k,v in source.items() if k in ('FAIL_TO_PASS','PASS_TO_PASS')}
    if tests:
        assert all(sum(by[k].values())==counts[k] for k in counts)
    outcome={'instance_id':iid,'arm':arm,'input_patch_sha256':hash_patch,'input_patch_bytes':len(raw),'run_id':run_id,'case_sha256':source_hash,
             'utc_start':utc,'utc_end':stamp(),'seconds':time.monotonic()-start,'official_exit':status,
             'official_summary':report.relative_to(HERE).as_posix(),'official_report_sha256':sha(report),
             'test_logs_sha256':pair_logs,'console_sha256':sha(work/'official_console.log'),'resolved':row.get('resolved'),
             'patch_applied':row.get('patch_applied'),'tests_status_present':bool(tests),'test_counts':by,
             'expected_case_test_counts':counts,'reported_error':row.get('error'),
             'has_before_log_heading':'Tests BEFORE model patch' in data,'has_after_log_heading':'Tests AFTER model patch' in data}
    receipt_file.parent.mkdir(exist_ok=True,parents=True);save(receipt_file,outcome)
    print(iid,arm,'resolved',outcome['resolved'],'tests_status_present',bool(tests),'elapsed',round(outcome['seconds']),flush=True)
    return True


def summarize():
    reports=[read(f) for f in sorted((HERE/'receipts').glob('*/*.json'))]
    summary={'time':stamp(),'coverage':len(reports),'calibration':{},'arms':{}}
    for key in ('empty','inert','gold',*ARMS):
        rows=[r for r in reports if r['arm']==key]
        summary['calibration' if key not in ARMS else 'arms'][key]={'n':len(rows),'resolved':sum(r['resolved'] is True for r in rows),
                    'tests_status':sum(r['tests_status_present'] for r in rows),'per_target':{r['instance_id']:r['resolved'] for r in rows}}
    save(HERE/'summary.json',summary)
    if reports:
        lightweight=['instance_id','arm','run_id','input_patch_bytes','input_patch_sha256','resolved','patch_applied','tests_status_present','seconds','official_summary','official_report_sha256']
        with (HERE/'per_trial.csv').open('w',newline='',encoding='utf8') as f:
            writer=csv.DictWriter(f,fieldnames=lightweight,extrasaction='ignore');writer.writeheader();writer.writerows(reports)


def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['calibrate','ready','summarize','manifest'])
    p.add_argument('--target',choices=TARGETS);p.add_argument('--arm',choices=ARMS)
    args=p.parse_args()
    if args.operation=='summarize':summarize();return
    if args.operation=='manifest':manifest();return
    if not (HERE/'image_manifest.json').is_file():manifest()
    jobs=('empty','inert','gold') if args.operation=='calibrate' else ((args.arm,) if args.arm else ARMS)
    for iid in ((args.target,) if args.target else TARGETS):
        for arm in jobs:
            grade(iid,arm);summarize()

if __name__=='__main__':main()

