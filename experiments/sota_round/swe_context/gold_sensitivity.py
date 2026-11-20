"""Post-score sensitivity to the benchmark's three multiply-linked cases. No reranking."""
import csv
import json
import re
from collections import defaultdict
import pyarrow.parquet as pq
from cards import DATA, HERE

def run():
    assert (HERE/'blind_commit.json').is_file()
    groups=defaultdict(list)
    for row in pq.read_table(DATA/'SWEContextBench_Relationship.parquet',columns=['related_instance_id','experience_instance_id']).to_pylist():
        if row['experience_instance_id'] not in groups[row['related_instance_id']]:
            groups[row['related_instance_id']].append(row['experience_instance_id'])
    library={}
    for f in (DATA/'traces').glob('*.jsonl'):
        for line in f.open(encoding='utf8'):
            try: row=json.loads(line)
            except ValueError:continue
            msg=row.get('message',{}).get('content')
            if row.get('type')=='user' and isinstance(msg,str) and 'problem_statement:' in msg:
                library[f.stem]=re.search(r'(?m)^\s*instance_id:\s*(\S+)',msg)[1];break
    queries=[r for r in csv.DictReader((HERE/'per_query.csv').open(encoding='utf8')) if r['group']=='lite']
    choices=[v['choice'] for v in sorted(map(json.loads,(HERE/'qwen_calls.jsonl').read_text(encoding='utf8').splitlines()), key=lambda v:v['ordinal'])]
    values=set(library.values())
    gold=[groups[r['instance_id']] for r in queries]
    selected=[library[k] for k in choices]
    scores={name:{'match1':sum(ans in lab for ans,lab in zip(selected,gl)), 'in_library':sum(bool(set(lab)&values) for lab in gl)} for name,gl in [('any',gold),('first_in_dated_release',[a[:1] for a in gold]),('last_in_dated_release',[a[-1:] for a in gold])]}
    scores['single_link_only']={'n':sum(len(a)==1 for a in gold),'match1':sum(v in a for v,a in zip(selected,gold) if len(a)==1)}
    scores['all_possible_one_per_task']=[sum(len(a)==1 and v in a for v,a in zip(selected,gold)),scores['any']['match1']]
    (HERE/'gold_sensitivity.json').write_text(json.dumps(scores,indent=2),encoding='utf8')
    print(json.dumps(scores))
if __name__=='__main__':run()

