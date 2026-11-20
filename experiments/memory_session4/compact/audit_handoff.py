"""Independent pre-outcome audit. Reads no report.json, labels, choices or scores."""
import sys, json, gzip, hashlib, collections, datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent
H=HERE.parent/'handoff'
sys.path.insert(0,str(H))
from writer import project, check_event, TEST
from common import sha
def read(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix=='.gz' else data)
def verify_lock(path):
    lock=read(path)
    mismatch=[name for name,digest in lock.items() if hashlib.sha256((path.parent/name).read_bytes()).hexdigest()!=digest]
    assert not mismatch,(str(path),mismatch)
    return len(lock)
locks={}
for f in ['input_lock.json','grade_lock.json','clean_setup_lock.json','clean/input_lock.json','shuffle/input_lock.json','control_grade_lock.json']:
    if (H/f).exists(): locks[f]=verify_lock(H/f)
receipts=read(H/'receipts.json.gz')
stats=collections.Counter()
cases=[]
affected=collections.defaultdict(list)
for model in ['claude','codex','gemini']:
    for path in sorted((H/'records'/model).glob('*.json.gz')):
        row=read(path)
        observed=project(row)
        assert observed==receipts[model+'|'+row['issue_id']]
        stats['rows']+=1
        stats[model+'_rows']+=1
        for j,turn in enumerate(row['turns']):
            event=check_event(turn['cmd'],turn)
            if not event or not event['visible']: continue
            stats['checks']+=1
            top=turn['cmd'].split('<<',1)[0]
            found=list(TEST.finditer(top))
            reasons=[]
            if len(found)>1: reasons.append('multiple tests')
            if top[found[-1].end():].strip(): reasons.append('trailing shell')
            if '<<' in turn['cmd']: reasons.append('heredoc')
            if event['out']!='ambiguous' and reasons:
                stats['diagnostic_bypasses_ambiguity']+=1
                stats[model+'_diagnostic_bypasses_ambiguity']+=1
                affected[model].append(row['issue_id'])
                cases.append({'model':model,'id':row['issue_id'],'turn':j,'reasons':reasons,
                              'command':turn['cmd'],'projected':event})
for m,ids in affected.items(): stats[m+'_affected_trajectories']=len(set(ids))
synthetic=[
    ('pytest a.py; pytest b.py',{'rc':1,'diag':'1 passed','visible_sha':'x'}),
    ('pytest a.py; python repro_b.py',{'rc':1,'diag':'1 passed','visible_sha':'x'}),
    ('pytest a.py; python repro_b.py',{'rc':0,'diag':'1 failed','visible_sha':'x'})
]
examples=[{'cmd':cmd,'input':e,'output':check_event(cmd,e)} for cmd,e in synthetic]
trace=read(H/'attestation/trace_checks.json.gz')
source_stats={}
for model in ['claude','codex','gemini']:
    rr=[r for r in trace if r['m']==model]
    source_stats[model]={'n':len(rr),'configured':dict(collections.Counter(r['configured'] for r in rr)),
                        'exact':sum(r['exact'] for r in rr),'empty_submission':sum(r['empty_submit'] for r in rr)}
original=read(H/'trace_listing.json.gz')
extra=read(H/'attestation/possible_duplicates.json.gz')
replicated_etags={key:sum(v.get(r['id'],{}).get('md5')==r.get('etag') for r in original if r['model']=='codex')
                  for key,v in extra.items()}
report={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'no_outcomes_read':True,
        'locks':locks,'projection_regeneration_equal':True,'counts':dict(stats),
        'synthetic_failures':examples,'source_checks':source_stats,'recomputed_etag_matches':replicated_etags}
(HERE/'handoff_audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
(HERE/'handoff_ambiguous_events.json').write_text(json.dumps(cases,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
print('REAL EXAMPLES')
for x in cases[:8]:print(json.dumps(x,ensure_ascii=True))

