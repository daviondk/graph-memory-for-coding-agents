"""Paired eligible-history delivery counts and stratified equal-coverage controls."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
T=ROOT.parent/'transfer'

def read(n):return json.loads((ROOT/n).read_text(encoding='utf8'))
def aggregate():
    for n,h in read('lock.json')['sha256'].items():
        q=ROOT/n if (ROOT/n).is_file() else T/n
        assert hashlib.sha256(q.read_bytes()).hexdigest()==h
    with (T/'per_question.csv').open(encoding='utf8',newline='') as f:
        truth={r['id']:r for r in csv.DictReader(f) if r['scope']=='repo_time'}
    rows=[]
    for x in read('blind.json'):
        t=truth[x['id']]; found=x['candidate'] is not None and x['candidate'] in t['gold'].split('|')
        assert found==(t['card_1']=='True')
        rows.append({**x,'all':bool(x['candidate']),'hit':found,'available':t['available']=='True'})
    assert len(rows)==len(truth)
    groups=defaultdict(list)
    for r in rows:
        if r['candidate']:groups[r['repo']].append(r)
    policies=['all','gate']+[f'{m}_{k}' for k in [25,50,75] for m in ['bm25','margin','symbol']]
    out={}
    per_repo={}
    for m in policies:
        selected=[r for r in rows if r[m]]
        hits=sum(r['hit'] for r in selected)
        by={g:{'pool':len(rs),'selected':sum(r[m] for r in rs),'top_hits':sum(r['hit'] for r in rs),'kept':sum(r['hit'] and r[m] for r in rs)} for g,rs in sorted(groups.items())}
        chance=sum(v['selected']*v['top_hits']/v['pool'] for v in by.values())
        out[m]={'deliveries':len(selected),'linked_delivered':hits,'precision':hits/len(selected) if selected else 0,'retained':hits/sum(r['hit'] for r in rows),'matched_random_expected':chance}
        per_repo[m]=by
    return {'queries':len(rows),'eligible':sum(r['available'] for r in rows),'methods':out,'by_repo':per_repo,'nonempty_repos':len(groups)}
def main():
    results=aggregate()
    (ROOT/'results.json').write_text(json.dumps(results,indent=1)+'\n',encoding='utf8')
    print(results['methods'])
if __name__=='__main__':main()

