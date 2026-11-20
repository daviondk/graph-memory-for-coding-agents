"""Freeze strata without loading the authors' solver outcomes."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
TRANSFER = ROOT.parent / 'transfer'

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def store(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf8')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    targets = {x['target']:x for x in read_csv(TRANSFER / 'query_times_lite.csv')}
    sources = {x['instance_id']:x for x in read_csv(TRANSFER / 'source_times_lite.csv')}
    assignments = []
    ordered = pq.read_table(ROOT / 'data_targets_train.parquet',columns=['target_id','prior_id','valid_target','excluded','exclusion_reason']).to_pylist()
    for v in ordered:
        t = targets.get(v['target_id'])
        s = sources.get(v['prior_id'])
        same_repo = bool(t and s and t['repo'].lower() == s['repo'].lower())
        status = 'unknown'
        if same_repo and t['target_pr'] == s['source_pr']:
            status = 'same_fix'
        elif same_repo and t['opening_complete']=='1' and s['source_merge']:
            status = 'past' if s['source_merge'] < t['cutoff_utc'] else 'later'
        assignments.append({**v,'stratum':status,'target_pr_url':t['target_pr_url'] if t else None,
                            'source_pr_url':s['source_url'] if s else None,'cutoff':t['cutoff_utc'] if t else None,
                            'source_merge':s['source_merge'] if s else None})
    store('strata.json',assignments)
    store('lock.json',{n:digest(ROOT / n) for n in ['PROTOCOL.md','assign.py','strata.json','data_targets_train.parquet']})
    print(len(assignments),Counter(x['stratum'] for x in assignments if x['valid_target']))
if __name__=='__main__':
    main()

