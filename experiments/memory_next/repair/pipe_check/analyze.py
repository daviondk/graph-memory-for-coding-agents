"""Analyze the frozen 20-command cohort; report all unverified instrumentation."""
from collections import Counter
import csv
import json
import re
import zipfile
from run import HERE,ROOT,read,save,sha

PATTERN=r'^\s*(?:FAILED\s+\S+::\S+|ERROR\s+(?:\S+::\S+|at setup|collecting)|.*\b[1-9]\d* (?:failed|errors?)\b(?:[,\s]|$).*)'
FAILURE=re.compile(PATTERN,re.I)


def visible(where):
    out=(where/'stdout.bin').read_bytes()+b'\n'+(where/'stderr.bin').read_bytes()
    return any(FAILURE.search(s) for s in out.decode('utf8','replace').splitlines())

def conf(rows,k):
    return {slot:sum(bool(r[k])==a and r['pytest_any_nonzero']==b for r in rows)
            for slot,a,b in [('tp',True,True),('fp',True,False),('tn',False,False),('fn',False,True)]}
def write_csv(name,rows):
    with (HERE/name).open('w',newline='',encoding='utf8') as stream:
        w=csv.DictWriter(stream,fieldnames=rows[0].keys())
        w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v) if isinstance(v,list) else v for k,v in r.items()})


def summarize():
    commands=[];pipelines=[];ref=read(ROOT/'action_audit.json')['tests']
    for idx,original in enumerate(ref,1):
        item=HERE/'raw'/f'{idx:02}'
        design=read(item/'design.json')
        assert all(design[k]==v for k,v in original.items()) and read(item/'complete.json')
        orig=read(item/'untouched'/'run.json')['native_shell_returncode']
        where=item/'instrumented';outer=read(where/'run.json')['native_shell_returncode']
        inner=[int(v) for v in (where/'pytest.tsv').read_text().splitlines()]
        pipes={}
        for line in (where/'pipeline.tsv').read_text().splitlines():
            i,ret,rc=line.split('\t')
            assert int(i) not in pipes
            pipes[int(i)]=(int(ret),[int(s) for s in rc.split()])
        reasons=[];planned=design['pipelines']
        if outer in (124,137):reasons.append('timeout_or_kill')
        if len(inner)!=len(planned) or len(pipes)!=len(planned):reasons.append('missing_sidecar')
        for j,desc in enumerate(planned):
            native=inner[j] if j<len(inner) else None
            rc,codes=pipes.get(desc['segment'],(None,[]))
            if rc is not None and (not codes or codes[0]!=native or codes[-1]!=rc or len(codes)!=len(desc['stages'])):reasons.append('rc_disagreement')
            filters=list(zip(desc['stages'],codes))
            pipelines.append({'command':idx,'pipeline':j+1,'native':native,'collect_only':desc['collect_only'],
                'outer':rc,'stages':desc['stages'],'codes':codes,'grep_no_match':sum(n=='grep' and v==1 for n,v in filters),
                'grep_error':sum(n=='grep' and v==2 for n,v in filters),'sigpipe_compatible':sum(v==141 for _,v in filters),
                'direct_diagnostic':(item/f'direct-{j+1:02d}'/'run.json').exists()})
        any_nonzero=(any(v!=0 for v in inner) if not reasons else None)
        commands.append({'command':idx,'issue':original['id'],'arm':original['arm'],'turn':original['turn'],'original_outer':int(original['outer_status'].split()[-1]),
            'untouched_outer':orig,'hooked_outer':outer,'verified':not reasons,'unverified_reasons':reasons,'pytest_rcs':inner,
            'pytest_any_nonzero':any_nonzero,'old_regex':bool(original['failure_evidence']),
            'untouched_regex':visible(item/'untouched'),'hooked_regex':visible(where)})
    verified=[r for r in commands if r['verified']];zero=[r for r in verified if r['hooked_outer']==0]
    def counts(key):return dict(Counter(p[key] for p in pipelines))
    def matrix(rlist):return {key:conf(rlist,key) for key in ('old_regex','untouched_regex','hooked_regex')}
    return {'n_commands':len(commands),'n_pipeline':len(pipelines),'verified':len(verified),'zero_outer_n':len(zero),
            'zero_outer_nonzero_native':sum(r['pytest_any_nonzero'] for r in zero),
            'original_zero_visible_failure':sum(r['old_regex'] and r['original_outer']==0 for r in commands),
            'instrumented_zero_visible_failure':sum(r['hooked_regex'] and r['hooked_outer']==0 for r in commands),
            'original_untouched_same_outer':sum(r['original_outer']==r['untouched_outer'] for r in commands),
            'instrumented_untouched_same_outer':sum(r['hooked_outer']==r['untouched_outer'] for r in commands),
            'original_untouched_same_regex':sum(r['old_regex']==r['untouched_regex'] for r in commands),
            'untouched_instrumented_same_regex':sum(r['untouched_regex']==r['hooked_regex'] for r in commands),
            'native_counts':counts('native'),'native_executing_tests_only':dict(Counter(p['native'] for p in pipelines if not p['collect_only'])),
            'collect_only_rc':dict(Counter(p['native'] for p in pipelines if p['collect_only'])),
            'grep_no_match':sum(p['grep_no_match'] for p in pipelines),'grep_error':sum(p['grep_error'] for p in pipelines),
            'sigpipe_compatible':sum(p['sigpipe_compatible'] for p in pipelines),
            'pytest_sigpipe_compatible':sum(p['native']==141 for p in pipelines),
            'timeouts':sum('timeout_or_kill' in r['unverified_reasons'] for r in commands),
            'historical_regex_vs_native_replay_and_new_regex':matrix(verified),'within_zero_outer':matrix(zero),
            'count_outer_by_native':dict(Counter(str(r['hooked_outer'])+'|'+str(r['pytest_any_nonzero']) for r in verified)),
            'source_cases':dict(Counter(r['issue'] for r in commands)),
            'commands':commands,'pipelines':pipelines}

def main():
    d=summarize(); save(HERE/'results.json',d)
    write_csv('commands.csv',d['commands']);write_csv('pipelines.csv',d['pipelines'])
    f=HERE/'raw.zip'
    with zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted((HERE/'raw').rglob('*')):
            if p.is_file():z.write(p,p.relative_to(HERE).as_posix())
    print(json.dumps({k:v for k,v in d.items() if k not in ['commands','pipelines']},ensure_ascii=False))
if __name__=='__main__':main()

