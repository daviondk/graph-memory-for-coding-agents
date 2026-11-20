"""Use identical reader code; transport option names only map public data to a two-alternative exercise."""
import shutil
from common import *
from writer import excerpt
from prepare_solver import anonymize
def main():
    dest=ROOT/'clean';dest.mkdir(exist_ok=True)
    for f in ('reader.py','common.py'):shutil.copyfile(ROOT/f,dest/f)
    rc=read('receipts.json.gz');issues=read('issues.json');cohort=[]
    docs={}
    for iid in issues:
        ps=[ROOT/'records'/m/(iid+'.json.gz') for m in ('claude','gemini')]
        if not all(x.is_file() for x in ps):continue
        v=[read(x.relative_to(ROOT)) for x in ps]
        if not all(r['traj_submission_matches'] is True for r in v):continue
        cohort.append(iid);docs[iid]=v
    ids=sorted(cohort,key=lambda i:sha('s4-judge-20261117'+i))[:96];data={}
    for i in ids:
        data[i]={'issue':anonymize(excerpt(issues[i]['problem_statement'],2850)),'options':{}}
        for alias,m,r in zip(('claude','codex'),('claude','gemini'),docs[i]):
            n=rc[m+'|'+i];data[i]['options'][alias]={'patch':anonymize(excerpt(r['patch'],3450)) or '(empty patch)',
                'latest':anonymize(n['latest_note']) or '(no retained verification)','witness':anonymize(n['witness_note']) or '(no retained verification)'}
    write('clean/cohort.json',sorted(cohort));write('clean/reader_inputs.json.gz',data)
    jobs=[{'issue':i,'arm':a,'reverse':rev} for i in ids for a in ('empty','latest','witness') for rev in (False,True)]
    jobs.sort(key=lambda j:sha('schedule4|'+canon(j)));write('clean/schedule.json',jobs)
    files=['reader.py','common.py','reader_inputs.json.gz','schedule.json','cohort.json']
    write('clean/input_lock.json',{f:sha((dest/f).read_bytes()) for f in files})
    write('clean_setup_lock.json',seal(['clean/input_lock.json','PROVENANCE_AMENDMENT.md','clean_setup.py','input_lock.json']))
    print('exact',len(cohort),'reader',len(ids),'assignments',len(jobs))
if __name__=='__main__':main()
