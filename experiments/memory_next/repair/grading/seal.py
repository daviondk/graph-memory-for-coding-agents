"""Verify primary grader outputs; summarize calibration without leaking held-out inputs to the solver."""
from collections import Counter, defaultdict
import csv
from pathlib import Path
import json
import re
import zipfile
from grade import ARMS, HERE, TARGETS, read, save, sha

def status_summary(text,which):
    mark=f'Tests {which} model patch'
    if mark not in text:
        return {}
    # Consume only the official enumerated test-status block.
    body=text.split(mark,1)[1]
    m=re.search(r'^Collected (\d+) test\(s\)\s*$',body,re.M)
    if not m:return {}
    count=int(m[1]);results=[]
    for line in body[m.end():].strip('\n').splitlines()[:count]:
        item=line.rsplit(': ',1)[-1].strip()
        if item:results.append(item)
    if count!=len(results):
        raise ValueError('Official collection count differs from log rows')
    return dict(Counter(results))

def main():
    groups={}
    for p in sorted((HERE/'receipts').glob('*/*.json')):
        r=read(p)
        summary_path=HERE/r['official_summary'];assert sha(summary_path)==r['official_report_sha256']
        run=summary_path.parent
        log=next((run/'logs'/'run_evaluation'/r['run_id']).glob('*/'+r['instance_id']))
        assert sha(run/'official_console.log')==r['console_sha256']
        for name,info in r['test_logs_sha256'].items():assert sha(log/name)==info['sha256']
        content=(log/'test_output.txt').read_text(encoding='utf8') if (log/'test_output.txt').is_file() else ''
        status={k:status_summary(content,k) for k in ('BEFORE','AFTER')}
        r['statuses']=status
        groups.setdefault(r['instance_id'],{})[r['arm']]=r
    output={'targets':{},'valid_positive_negative_controls':0,'assignments':{},'pairwise':{}}
    pairs=defaultdict(list)
    for iid in TARGETS:
        arms=groups.get(iid,{})
        if not all(k in arms for k in ('gold','inert','empty')):
            output['targets'][iid]={'calibration_complete':False}
            continue
        valid=bool(arms['gold']['resolved'] and arms['gold']['tests_status_present'] and
                   not arms['inert']['resolved'] and arms['inert']['tests_status_present'] and
                   arms['gold']['statuses']['BEFORE'] and arms['gold']['statuses']['AFTER'] and
                   arms['inert']['statuses']['BEFORE'] and arms['inert']['statuses']['AFTER'])
        output['valid_positive_negative_controls']+=valid
        output['targets'][iid]={'calibration_complete':True,'calibrated':valid,'empty_not_submitted':not arms['empty']['resolved'] and not arms['empty']['tests_status_present'],
              'inert_resolved':arms['inert']['resolved'],'gold_resolved':arms['gold']['resolved'],
              'inert_counts':arms['inert']['test_counts'],'gold_counts':arms['gold']['test_counts'],
              'inert_status_before_after':arms['inert']['statuses'],'gold_status_before_after':arms['gold']['statuses']}
        for a in ARMS:
            if a in arms:
                r=arms[a]
                item={'instance_id':iid,'arm':a,'resolved':r['resolved'],'patch_applied':r['patch_applied'],'has_test_status':r['tests_status_present'],
                      'calibrated':valid,'status_counts':r['statuses'],'counts_F2P_P2P':r['test_counts'],'infrastructure_or_patch_error':r['reported_error'],'patch_bytes':r['input_patch_bytes']}
                output['assignments'].setdefault(a,[]).append(item)
        if set(ARMS)<=set(arms):
            for a,b in [('on_demand','brief'),('eager','brief'),('on_demand','eager')]:
                pairs[a+'__vs__'+b].append({'instance_id':iid,'calibrated':valid,'delta':int(arms[a]['resolved'])-int(arms[b]['resolved'])})
    for k,rr in pairs.items():
        v=[r['delta'] for r in rr]
        output['pairwise'][k]={'n':len(v),'wins':v.count(1),'losses':v.count(-1),'ties':v.count(0),'rows':rr}
    save(HERE/'calibration_and_graded.json',output)
    raw_zip=HERE/'official_execution.zip'
    temp_zip=raw_zip.with_suffix('.partial.zip')
    with zipfile.ZipFile(temp_zip,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted((HERE/'attempts').rglob('*')):
            if not path.is_file():continue
            # A fresh copy of the benchmark gold production patch is not required to verify the official outputs.
            if path.name=='prediction.json' or path.name=='patch.diff':continue
            z.write(path,path.relative_to(HERE).as_posix())
        for path in sorted((HERE/'receipts').rglob('*.json')):z.write(path,path.relative_to(HERE).as_posix())
    temp_zip.replace(raw_zip)
    seal_files=['grade.py','seal.py','watch.py','verify_archive.py','README_RU.md','upstream_pin.json',
                'image_manifest.json','per_trial.csv','summary.json','calibration_and_graded.json','official_execution.zip',
                'check_patch_transport.py','patch_transport.json']
    if (HERE/'test_path_audit.json').is_file():
        seal_files.extend(['audit_test_paths.py','test_path_audit.json','matched_groups.json'])
    save(HERE/'seal.json',{n:sha(HERE/n) for n in seal_files})
    print('Calibrated',output['valid_positive_negative_controls'],'of',len(TARGETS),'completed real grades',sum(map(len,output['assignments'].values())),flush=True)

if __name__=='__main__':main()

