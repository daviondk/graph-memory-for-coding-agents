"""Collect actual predecessor observations and a disjoint future case roster."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from common import *
def prepare(file):
    name=file.stem
    bad=(UP/'python_programs'/f'{name}.py').read_text(encoding='utf8')
    good=(UP/'correct_python_programs'/f'{name}.py').read_text(encoding='utf8')
    tests=(UP/'python_testcases'/f'test_{name}.py').read_text(encoding='utf8')
    roster={}
    for line in file.read_text(encoding='utf8').splitlines():
        args,expected=json.loads(line)
        k=sha(obj(args))
        if k in roster:assert roster[k]['expected']==expected
        roster[k]={'input':args,'expected':expected,'key':k}
    cases=sorted(roster.values(),key=lambda c:c['key'])
    for i,c in enumerate(cases):c['part']='future' if i%2 else 'observed'
    fixed=grade(name,good,cases)
    original=grade(name,bad,cases)
    rows={r['key']:r for r in original}
    eligible=len(cases)>=3 and all(r['ok'] for r in fixed)
    notes=[]
    for c in cases[::2]:
        r=rows[c['key']]
        note=obj({'arguments':c['input'],'observed':r['observation'],'expected':c['expected'],'passed':r['ok']})
        notes.append({'key':c['key'],'ok':r['ok'],'text':note if len(note)<=450 else note[:285]+'...[excerpt]...'+note[-148:]})
    rec=notes[-2:]; shortest=sorted(notes,key=lambda s:(len(s['text']),s['key']))
    failures=[n for n in shortest if not n['ok']]
    passes=[n for n in notes if n['ok']]
    wit=([failures[0]]+([passes[0]] if passes else failures[1:2])) if failures else shortest[:2]
    def contents(n):return '\n'.join(v['text'] for v in n)[:6000]
    mem={k:contents(a) for k,a in [('empty',[]),('recent',rec),('witness',wit),('full',notes)]}
    save('fixtures/'+name+'.json',{'name':name,'cases':cases,'correct_controls':fixed,'original':original,'buggy_source':bad,'correct_source_sha256':sha(good),'official_test':tests,'notes':notes,'memory':mem})
    return {'name':name,'unique_cases':len(cases),'original_public_rows':len(file.read_text().splitlines()),'correct_pass':sum(r['ok'] for r in fixed),'eligible':eligible,'example_in_source':'>>>' in bad,'reason':None if eligible else ('fewer_than_3' if len(cases)<3 else 'reference_control_mismatch')}
def main():
    files=sorted((UP/'json_testcases').glob('*.json'))
    with ThreadPoolExecutor(2) as pool:rows=list(pool.map(prepare,files))
    save('roster.json',rows)
    jobs=[{'name':r['name'],'arm':a} for r in rows if r['eligible'] for a in ARMS]
    jobs.sort(key=lambda j:sha('20261117|'+obj(j)))
    save('schedule.json',jobs)
    paths=['PROTOCOL.md','common.py','container_runner.py','prepare.py','roster.json','schedule.json']+['fixtures/'+r['name']+'.json' for r in rows]
    save('input_lock.json',{'utc':utc(),'files':freeze(paths)})
    print('eligible',sum(r['eligible'] for r in rows),'of',len(rows),'assignments',len(jobs),flush=True)
if __name__=='__main__':main()

