"""Submit the eight locked continuation patches to the unmodified author evaluator.

Independent containers, the same four pinned fixtures, and no new calls to the solver.
"""
import argparse
import csv
import json
import shutil
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path
from statistics import mean

HOME_DIR=Path(__file__).resolve().parent
ROOT=HOME_DIR.parent
PRIMARY=ROOT.parent/'repair'/'grading'
sys.path.insert(0,str(PRIMARY))
import grade
from audit_test_paths import paths
from grade import read, save, sha
from seal import status_summary

ARMS=('last_two','manifest')
CASES=grade.TARGETS


def pinned_inputs():
    parent=read(PRIMARY/'summary.json')
    assert parent['coverage']==24 and all(len(a['per_target'])==4 for a in parent['arms'].values())
    original=read(PRIMARY/'calibration_and_graded.json')
    assert original['valid_positive_negative_controls']==len(CASES)
    image=PRIMARY/'image_manifest.json'
    source=PRIMARY/'upstream_pin.json'
    for name in (image,source):
        dest=HOME_DIR/name.name
        if dest.exists():assert sha(dest)==sha(name)
        else:shutil.copyfile(name,dest)
    grade.ROOT,grade.HERE,grade.ARMS=ROOT,HOME_DIR,ARMS
    grade.manifest()
    jobs=[tuple(v) for v in read(ROOT/'assignments.json')]
    assert len(jobs)==8 and set(jobs)=={(i,a) for i in CASES for a in ARMS}
    assert (ROOT/'end_lock.json').is_file()
    proof={'repair_author_evaluator_sha256':sha(grade.UPSTREAM/'swebench_memory'/'harness'/'run_evaluation.py'),
           'grader_wrapper_sha256':sha(PRIMARY/'grade.py'),
           'upstream_pin_sha256':sha(source),'image_manifest_sha256':sha(image),
           'continuation_end_lock_sha256':sha(ROOT/'end_lock.json'),'continuation_assignments_sha256':sha(ROOT/'assignments.json'),
           'initial_brief_receipts_sha256':{},'controls':{}}
    parent_dir=HOME_DIR/'parents'
    parent_dir.mkdir(exist_ok=True)
    for iid in CASES:
        initial=PRIMARY/'receipts'/iid/'brief.json'
        local=parent_dir/(iid+'.json')
        if local.exists():assert sha(local)==sha(initial)
        else:shutil.copyfile(initial,local)
        proof['initial_brief_receipts_sha256'][iid]=sha(local)
        for ref in ('gold','inert','empty'):
            r=read(PRIMARY/'receipts'/iid/(ref+'.json'))
            assert r['case_sha256']==next(x['case_file_sha256'] for x in read(image)['targets'] if x['instance_id']==iid)
            assert sha(PRIMARY/r['official_summary'])==r['official_report_sha256']
            assert r['resolved']==(ref=='gold') and r['tests_status_present']==(ref!='empty')
            proof['controls'].setdefault(iid,{})[ref]={'resolved':r['resolved'],'tests_status':r['tests_status_present'],
                                                    'official_report_sha256':r['official_report_sha256'],'run_id':r['run_id']}
    dest=HOME_DIR/'provenance.json'
    if dest.exists():assert read(dest)==proof
    else:save(dest,proof)
    return jobs


def finish(jobs):
    issues={}
    report_rows=[]
    groups={}
    for iid,arm in jobs:
        case=read(grade.DATA/'case_metadata'/(iid+'.json'))
        pr=case['repo']+'#'+str(case['pull_number'])
        baseline=read(PRIMARY/'receipts'/iid/'brief.json')
        row=read(HOME_DIR/'receipts'/iid/(arm+'.json'))
        assert row['case_sha256']==baseline['case_sha256']
        candidate=ROOT/'runs'/iid/arm/'candidate.patch'
        assert row['input_patch_sha256']==sha(candidate)
        status=bool(row['resolved'])
        body=read(HOME_DIR/row['official_summary'])
        assert row['official_report_sha256']==sha(HOME_DIR/row['official_summary'])
        assert status==body[iid]['resolved']
        aux=read(ROOT/'runs'/iid/arm/'complete.json')
        assert aux['patch_sha256']==sha(candidate)
        summary={'instance_id':iid,'pr':pr,'arm':arm,'resolved':status,'initial_brief_resolved':baseline['resolved'],
                 'initial_brief_bytes':baseline['input_patch_bytes'],'candidate_bytes':row['input_patch_bytes'],'changed_vs_input':baseline['input_patch_sha256']!=sha(candidate),
                 'patch_applied':row['patch_applied'],'tests_status':row['tests_status_present'],'counts':row['test_counts'],
                 'error':row['reported_error'],'verifier_file_overlaps':len(paths(case['test_patch']) & paths(candidate.read_text(encoding='utf8')))}
        tests_dir=next((HOME_DIR/row['official_summary']).parent.glob('logs/run_evaluation/*/*/'+iid))
        log_text=(tests_dir/'test_output.txt').read_text(encoding='utf8') if (tests_dir/'test_output.txt').is_file() else ''
        summary['status_counts']={side:status_summary(log_text,side) for side in ('BEFORE','AFTER')}
        for k in ('calls','input_tokens','output_tokens','finish_reason','elapsed_s'):
            if k in aux: summary[k]=aux[k]
        report_rows.append(summary)
        issues.setdefault(iid,{})[arm]=int(status)
        groups.setdefault(pr,{}).setdefault(arm,[]).append(int(status))
    dif=[arms['manifest']-arms['last_two'] for arms in issues.values()]
    rates={arm:{'issue_rate':mean(arms[arm] for arms in issues.values()),
                'equal_pr_weighted_rate':mean(mean(pr[arm]) for pr in groups.values()),
                'tested':sum(r['tests_status'] for r in report_rows if r['arm']==arm),
                'nonempty':sum(bool(r['candidate_bytes']) for r in report_rows if r['arm']==arm)} for arm in ARMS}
    res={'n_issues':len(issues),'n_pr':len(groups),'completed':len(report_rows),'paired_manifest_minus_last_two':{'wins':dif.count(1),'losses':dif.count(-1),'ties':dif.count(0)},
         'rates':rates,'issues':issues,'groups':groups,'rows':report_rows}
    save(HOME_DIR/'summary.json',res)
    with (HOME_DIR/'per_trial.csv').open('w',encoding='utf8',newline='') as f:
        cols=list(report_rows[0].keys())
        writer=csv.DictWriter(f,fieldnames=cols)
        writer.writeheader()
        for row in report_rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,dict) else v for k,v in row.items()})
    dst=HOME_DIR/'official_execution.zip'
    partial=dst.with_suffix('.partial.zip')
    with zipfile.ZipFile(partial,'w',zipfile.ZIP_DEFLATED) as z:
        for sub in ('attempts','receipts','parents'):
            for path in sorted((HOME_DIR/sub).rglob('*')):
                if path.is_file() and path.name not in ('prediction.json','patch.diff'):
                    z.write(path,path.relative_to(HOME_DIR).as_posix())
    partial.replace(dst)
    filenames=['driver.py','verify.py','README_RU.md','image_manifest.json','upstream_pin.json','summary.json',
               'per_trial.csv','official_execution.zip','provenance.json']
    save(HOME_DIR/'seal.json',{file:sha(HOME_DIR/file) for file in filenames})
    print('Completed eight independent wrapper evaluations',flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--wait',action='store_true')
    args=p.parse_args()
    if args.wait:
        while not (ROOT/'end_lock.json').is_file() or not (PRIMARY/'test_path_audit.json').is_file():
            time.sleep(10)
    jobs=pinned_inputs()
    for iid,arm in jobs:
        assert grade.grade(iid,arm)
    finish(jobs)


if __name__=='__main__':main()

