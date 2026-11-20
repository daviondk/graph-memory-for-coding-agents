"""Run in the extracted archive, using Python standard library only."""
import argparse,csv,gzip,hashlib,json,zipfile
from collections import Counter
from pathlib import Path
root=Path(__file__).resolve().parent
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def j(path):return json.loads((root/path).read_text(encoding="utf-8-sig"))
def lines(path):return [json.loads(x) for x in (root/path).read_text(encoding="utf-8-sig").splitlines() if x]
def csvrows(path):
    with (root/path).open(encoding="utf-8-sig",newline="") as fp:return list(csv.DictReader(fp))
parser=argparse.ArgumentParser(description="Check the archive offline. By default also replay the reported final comparisons.")
parser.add_argument('--manifest-only',action='store_true',help="Check transport integrity without opening outcomes or certifying finished experiments.")
args=parser.parse_args()
mf=(root/'MANIFEST.sha256').read_text(encoding='utf8').splitlines()
members=set()
for line in mf:
    h,name=line.split('  ',1)
    relative=Path(name)
    assert name not in members and not relative.is_absolute() and '..' not in relative.parts,name
    members.add(name)
    assert digest(root/name)==h,name
print('SHA-256:',len(mf),'files')
if args.manifest_only:raise SystemExit(0)
for arm in ('run','followup'):
    metrics=j('boundary/'+arm+'/results.json')['methods'];rows=csvrows('boundary/'+arm+'/per_question.csv')
    assert len(rows)==470 and len(set(r['id'] for r in rows))==470
    for m,s in metrics.items():
        v=[int(r[m])-int(r['parent']) for r in rows]
        assert s['win']==v.count(1) and s['loss']==v.count(-1)
        assert sum(int(r[m]) for r in rows)==s['all']
print('Papr matched comparisons, 470 questions per endpoint')
for track in ('action','action_text'):
    graded=lines(track+'/graded.jsonl');assign=lines(track+'/assigned.jsonl');cs=lines(track+'/canaries.jsonl')
    results=j(track+'/action_results.json');byid={r['id']:r for r in graded}
    assert len(byid)==len(graded)==len(assign)==102 and len(cs)==103
    assert all(c['ok']==(c['arm'] in ('isolation','informed')) for c in cs)
    for arm,s in results['arms'].items():
        subset=[a for a in assign if a['arm']==arm];assert len(subset)==34
        assert sum(byid[a['id']]['ok'] for a in subset)==s['successes']
    zipped=root/track/'grading-evidence.zip'
    if zipped.exists():
        with zipfile.ZipFile(zipped) as z:assert z.testzip() is None
    print(track,[(a,s['successes']) for a,s in results['arms'].items()])
a=j('dretr/results.json');assert a['successful_all5']['witness']==391 and a['successful_all5']['position_control']==393 and len(lines('dretr/ranks.jsonl'))==500
coding=j('coding/results.json');assert coding['n']==len({r['instance_id'] for r in csvrows('coding/score_rows.csv')})==23
print('DRETR and SWE-Explore sample sizes checked. See individual track scripts for official scorers and model reruns.')

holdout=lines('coding_holdout/rows.jsonl')
assert len({v['instance_id'] for v in holdout})==j('coding_holdout/results.json')['n']==30
stages=lines('vibe_memory/stage_rows.jsonl')
assert len(stages)==333 and len({(v['instance_id'],v['method']) for v in stages})==333
paths=lines('vibe_memory/path_rows.jsonl')
assert len(paths)==333
for method,expected in [('action_receipt',102),('raw_bm25',59),('echo_capped',57)]:
    subset=[v for v in paths if v['method']==method]
    assert len(subset)==111 and sum(any(p['exists'] for p in v['paths']) for v in subset)==expected
scores=csvrows('prior_files/scores.csv')
assert len({v['id'] for v in scores})==111
for method,metrics in j('prior_files/results.json')['per_method'].items():
    assert sum(int(v[method]) for v in scores)==metrics['success']
for folder,episodes in [('vibe',8),('vibe/qwen38_27b',20),('vibe/in_loop',8)]:
    calls=csvrows(folder+'/episode_calls.csv'); usage=j(folder+'/exact_usage.json')
    assert len({(v['target'],v['arm'],v['seed']) for v in calls})==episodes
    assert len({v['response_id'] for v in calls})==len(calls)
    assert sum(int(v['prompt_tokens']) for v in calls)==sum(t['prompt_tokens'] for t in usage['by_episode'])
    assert sum(int(v['completion_tokens']) for v in calls)==sum(t['completion_tokens'] for t in usage['by_episode'])
    summary=j(folder+'/results.json');attempts=lines(folder+'/attempts.jsonl')
    assert len(attempts)==summary['graded_attempts']==episodes
    assert len({(a['target'],a['method'],a['seed']) for a in attempts})==episodes
    assert summary['evidence_sha256']==digest(root/folder/'execution_evidence.zip')
    for method,totals in summary['by_method'].items():
        armrows=[a for a in attempts if a['method']==method]
        assert totals['episodes']==len(armrows) and totals['resolved']==sum(a['resolved'] for a in armrows)
        assert totals['tests_executed']==sum(a['test_executed'] for a in armrows)
    if folder=='vibe/in_loop':
        delivery=j(folder+'/delivery.json'); delivered=delivery['rows']
        assert len(delivered)==episodes
        keyed={(a['target'],a['method'],a['seed']):a for a in attempts}
        for row in delivered:
            source=keyed.pop((row['target'],row['method'],row['seed']))
            assert row['resolved']==source['resolved'] and row['total_input_tokens']==source['input_tokens']
        for arm,stats in delivery['policy_arms'].items():
            subset=[r for r in delivered if r['method']==arm]
            assert sum(r['exposed'] for r in subset)==stats['exposures']
        with zipfile.ZipFile(root/folder/'transport_evidence.zip') as z:assert z.testzip() is None
print('VibeMemBench file predictions and exact 8B/27B solver usage checked.')
assert j('within_task/run.json')['histories']==2470
assert j('within_task/alias_summary.json')['cohorts']['primary']['n']==2797
with zipfile.ZipFile(root/'within_task/ledgers.zip') as z:assert z.testzip() is None
locked=j('swe_context/blind_commit.json')
for name,sha in locked.items():assert digest(root/'swe_context'/name)==sha
source=j('swe_context/source.json')
source_names=[entry['relative'] for entry in source['files']]
assert len(source_names)==len(set(source_names))==402
assert sum(name.startswith('traces/') and name.endswith('.jsonl') for name in source_names)==300
assert sum(name.startswith('case_metadata/') and name.endswith('.json') for name in source_names)==99
assert all(len(entry['sha256'])==64 and entry['size']>0 for entry in source['files'])
rows=csvrows('swe_context/per_query.csv')
outcomes=j('swe_context/results.json')
for group,values in outcomes['groups'].items():
    subset=[row for row in rows if row['group']==group or (group=='extension_available' and row['group']=='extension' and row['available']=='1')]
    assert len(subset)==values['n']
    for name,total in values['scores'].items():
        assert sum(int(row[name]) for row in subset)==total
calls=lines('swe_context/qwen_calls.jsonl')
assert len(calls)==len({v['ordinal'] for v in calls})==99
for v in calls:assert v['choice'] in v['order'] and len(set(v['order']))==5
assert outcomes['llm_cost']['input']==sum(v['usage']['prompt_tokens'] for v in calls)
assert outcomes['llm_cost']['output']==sum(v['usage']['completion_tokens'] for v in calls)
for name,sha in outcomes['external_prediction_hashes'].items():
    key=name+'.json'
    assert digest(root/'swe_context'/key)==sha==j('swe_context/'+name+'_pin.json')['sha256'][key]
print('SWE-ContextBench full predictions, result counts and Qwen choices verified.')
from swe_context import check_choices
check_choices.main()
for folder,expected_ret,expected_stale,expected_n in [('read_cache',270,0,54348),('read_cache/replication',1,0,1792)]:
    with zipfile.ZipFile(root/folder/'ledgers.zip') as z:assert z.testzip() is None
    record=j(folder+'/summary.json')
    if folder=='read_cache':
        arms=record['arms'];population=record['counts']
    else:
        arms=record['policies'];population=record['population']
        assert arms['write_through']['correct']==4 and arms['write_through'].get('stale',0)==0
    assert population['eligible']==expected_n
    assert (arms['selective']['correct'],arms['selective'].get('stale',0))==(expected_ret,expected_stale)
    order=j(folder+'/runtime.json')['arms']
    counts={name:Counter() for name in order}
    observed=0
    with zipfile.ZipFile(root/folder/'ledgers.zip') as z:
        with gzip.open(z.open('queries.jsonl.gz'),'rt',encoding='utf8') as file:
            for line in file:
                obs=json.loads(line);observed+=1
                assert len(obs['arms'])==len(order)
                for name,retrieval in zip(order,obs['arms']):
                    if retrieval is not None:counts[name][retrieval[2]]+=1
    assert observed==expected_n
    for name,totals in counts.items():
        for outcome in ['correct','stale']:
            assert totals[outcome]==arms[name].get(outcome,0),(folder,name,totals)
print('Strict byte-equality replay on both independent tool corpora verified.')

