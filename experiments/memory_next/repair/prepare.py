"""Extract only the solver-visible projection. No official target patch, test list, or grader result is read."""
from pathlib import Path
import csv, hashlib, json, time
import requests
import pyarrow.parquet as pq
HERE=Path(__file__).resolve().parent
PREV=HERE.parents[1]/'sota_round'/'swe_context'
DATA=Path('D:/CodexResearch/x20-swe-context')
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def save(name,obj):(HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
def clip(t,n):return ' '.join(t.split()[:n])
qs=pq.read_table(DATA/'SWEContextBench_Related_Lite.parquet',columns=['instance_id','repo','base_commit','problem_statement','created_at']).to_pylist()
cards={c['key']:c for c in json.loads((PREV/'cards.json').read_text(encoding='utf8'))}
picks={r['ordinal']:r['choice'] for r in map(json.loads,(PREV/'qwen_calls.jsonl').read_text(encoding='utf8').splitlines())}
ids={r['trace_key']:r['instance_id'] for r in csv.DictReader((PREV/'evaluation_library.csv').open(encoding='utf8'))}
rows=[]
for i,x in enumerate(qs):
    if x['repo'] not in ('psf/requests','pallets/flask'):continue
    iid=x['instance_id']
    key=picks[i];card=cards[key]
    rows.append({'id':iid,'repo':x['repo'],'commit':x['base_commit'],'image':'jiayuanz3/swecontextbench:'+iid.replace('__','.').lower(),'question':x['problem_statement'],'date':str(x['created_at']),'ordinal':i,'source_key':key,'source_id':ids[key],'symptom':clip(card['symptom'],175),'closure':clip(card['closure'],90),'edits':clip(card['edits'],40)})
rows.sort(key=lambda r:r['id'])
assert len(rows)==4
arms=['brief','eager','on_demand']
orders={r['id']:sorted(arms,key=lambda a:digest('next-repair|'+r['id']+'|'+a)) for r in rows}
save('inputs.json',rows)
save('assignments.json',[(r['id'],orders[r['id']][k]) for k in range(3) for r in rows])
for r in rows:print(r['id'],r['source_id'],r['date'])

