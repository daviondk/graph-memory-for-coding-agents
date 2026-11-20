"""Export two evaluation-only, byte-verified lookup tables after the prediction lock."""
import csv
import hashlib
import json
import os
import re
from pathlib import Path
import pyarrow.parquet as pq

here = Path(__file__).resolve().parent
data = Path(os.environ.get('SWE_CONTEXT_DATA', 'D:/CodexResearch/x20-swe-context'))
assert (here / 'blind_commit.json').is_file()
source = json.loads((here / 'source.json').read_text(encoding='utf8'))
hashes = {row['relative']: row['sha256'] for row in source['files']}

def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()

parquet = data / 'SWEContextBench_Relationship.parquet'
assert digest(parquet) == hashes[parquet.name]
relations = pq.read_table(parquet, columns=['related_instance_id','experience_instance_id']).to_pylist()
with (here / 'evaluation_relations.csv').open('w', encoding='utf8', newline='') as output:
    writer = csv.DictWriter(output, fieldnames=['related_instance_id','experience_instance_id'])
    writer.writeheader()
    writer.writerows(relations)
with (here / 'evaluation_library.csv').open('w', encoding='utf8', newline='') as output:
    writer = csv.writer(output)
    writer.writerow(['trace_key','instance_id'])
    for file in sorted((data / 'traces').glob('*.jsonl')):
        assert digest(file) == hashes['traces/'+file.name]
        for line in file.read_text(encoding='utf8').splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            value = row.get('message',{}).get('content')
            if row.get('type')=='user' and isinstance(value,str) and 'problem_statement:' in value:
                match = re.search(r'(?m)^\s*instance_id:\s*(\S+)', value)
                assert match, file
                writer.writerow([file.stem, match[1]])
                break
        else:
            raise ValueError('Prior source has no original user issue '+file.name)
