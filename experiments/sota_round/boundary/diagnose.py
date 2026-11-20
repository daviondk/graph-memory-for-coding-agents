"""Post-scoring error accounting; never used for method choice or generation."""
import csv,hashlib,json,math,statistics,sys
from collections import Counter
from pathlib import Path
src,papr,here=map(Path,sys.argv[1:])
data=json.loads(src.read_text(encoding='utf8'))
def rows(p):
    return [json.loads(l) for l in p.open(encoding='utf8') if l.strip()]
ranks={r['question_id']:r for r in rows(papr)}
requests={r['row']:r for r in rows(here/'followup'/'requests.jsonl')}
decisions=rows(here/'followup'/'predictions.jsonl')
cases=[];selection=Counter();judges=[]
for i,q in enumerate(data):
    abst=q['question_id'].endswith('_abs')
    if i in requests:
        req=requests[i];log=json.loads((here/'followup'/'logs'/(req['id']+'.json')).read_text(encoding='utf8'))
        tail=log['attempts'][-1]
        selection['abstention' if abst else 'scoreable']+=1
        judges.append({'row':i,'request':req['id'],'model':log['model'],'cli_version':log['cli_version'],'reasoning_effort':log['reasoning_effort'],'prompt_sha256':log['prompt_sha256'],'status':log['status'],'elapsed_s':tail['elapsed_s'],'attempts':len(log['attempts']),'tool_actions':len(tail['actions']),'input_tokens':log['usage']['input_tokens'],'output_tokens':log['usage']['output_tokens'],'cached_tokens':log['usage']['cached_input_tokens'],'decision':decisions[i]['status'],'final_slots':decisions[i]['orders']['slate']})
    if abst:continue
    gold=set(q['answer_session_ids']);ids=ranks[q['question_id']]['top20_session_ids']
    missed=gold-set(ids[:5])
    if not missed:continue
    req=requests.get(i)
    show={ids[k] for k in req['map'].values()} if req else set()
    cases.append({'row':i,'question_id':q['question_id'],'type':q['question_type'],'gold_count':len(gold),'missing_count_at_5':len(missed),'ranks_of_missing':','.join(str(ids.index(s)+1) if s in ids else '>20' for s in sorted(missed)),'recoverable_at_5':len(gold)<=5 and gold<=set(ids),'recoverable_one_swap':len(gold)<=5 and gold<=set(ids) and len(missed)==1,'reviewed':bool(req),'all_gold_on_screen':gold<=show,'result_after_review':decisions[i]['status']})
with (here/'error_cases.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(cases[0]));w.writeheader();w.writerows(cases)
(here/'hosted_decisions.jsonl').write_text(''.join(json.dumps(j)+'\n' for j in judges),encoding='utf8')
r={'total_misses':len(cases),'recoverable':sum(z['recoverable_at_5'] for z in cases),'one_swap':sum(z['recoverable_one_swap'] for z in cases),'reached_review':sum(z['recoverable_at_5'] and z['reviewed'] for z in cases),'all_on_screen':sum(z['recoverable_at_5'] and z['all_gold_on_screen'] for z in cases),'selection':dict(selection),'mean_hosted_wall':statistics.mean(j['elapsed_s'] for j in judges),'sum_hosted_wall':sum(j['elapsed_s'] for j in judges),'hosted_usage_sum':{k:sum(j[k] for j in judges) for k in ('tool_actions','attempts','input_tokens','cached_tokens','output_tokens')}}
(here/'diagnostics.json').write_text(json.dumps(r,indent=2),encoding='utf8')
print(r)

