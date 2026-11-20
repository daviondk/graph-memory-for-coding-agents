"""Run in the extracted archive, using Python standard library only."""
import csv,hashlib,io,json,math,zipfile
from pathlib import Path
root=Path(__file__).resolve().parent
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def j(path):return json.loads((root/path).read_text(encoding="utf-8-sig"))
def lines(path):return [json.loads(x) for x in (root/path).read_text(encoding="utf-8-sig").splitlines() if x]
def csvrows(path):
    with (root/path).open(encoding="utf-8-sig",newline="") as fp:return list(csv.DictReader(fp))
mf=(root/'MANIFEST.sha256').read_text(encoding='utf8').splitlines()
for line in mf:
    h,name=line.split('  ',1)
    assert digest(root/name)==h,name
print('SHA-256:',len(mf),'files')
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

