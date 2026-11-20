from common import *
from writer import excerpt
def anonymize(t):
    import re
    return re.sub(r'(?i)claude[- ](?:opus|sonnet)|gpt[- ]5[\w. -]*(?:codex)|gemini[- ]3[\w. -]*flash','[model]',t)
def main():
    issues=read('issues.json'); receipts=read('receipts.json.gz')
    ids=sorted(issues,key=lambda i:sha('s4-judge-20261117'+i))[:96]
    source={}
    for iid in ids:
        source[iid]={'issue':anonymize(excerpt(issues[iid]['problem_statement'],2850)),'options':{}}
        for m in ('claude','codex'):
            rr=read('records/'+m+'/'+iid+'.json.gz');n=receipts[m+'|'+iid]
            source[iid]['options'][m]={'patch':anonymize(excerpt(rr['patch'],3450)) or '(empty patch)',
                'latest':anonymize(n['latest_note']) or '(no retained verification)', 'witness':anonymize(n['witness_note']) or '(no retained verification)'}
    write('reader_inputs.json.gz',source)
    jobs=[{'issue':i,'arm':a,'reverse':rev} for i in ids for a in ('empty','latest','witness') for rev in (False,True)]
    jobs.sort(key=lambda j:sha('schedule4|'+canon(j)));write('schedule.json',jobs)
    files=['PROTOCOL.md','writer.py','common.py','fetch.py','prepare_solver.py','reader.py','issues.json','trace_listing.json.gz','asset_listing.json.gz','reader_inputs.json.gz','receipts.json.gz','schedule.json']
    files += [f.relative_to(ROOT).as_posix() for f in (ROOT/'records').rglob('*.gz')]
    write('input_lock.json',seal(files));print('locked',len(files),len(jobs),'assignments')
if __name__=='__main__':main()
