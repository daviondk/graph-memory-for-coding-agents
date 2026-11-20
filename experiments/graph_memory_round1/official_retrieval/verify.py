"""Offline checks using the official parquet, and deterministic replay in an isolated folder."""
import csv
import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

import rank
import score


def main():
    local = rank.HERE
    data = Path('D:/CodexResearch/x20-swe-context')
    tables = ['SWEContextBench_Relationship','SWEContextBench_Related_Lite','SWEContextBench_Related']
    receipts = {name:rank.sha(data/(name+'.parquet')) for name in tables}
    original = rank.read(rank.SOURCE/'source.json')
    pinned = {Path(r['relative']).stem:r['sha256'] for r in original['files']}
    assert all(pinned[t] == receipts[t] for t in receipts)
    relation = pq.read_table(data/(tables[0]+'.parquet'),columns=['related_instance_id','experience_instance_id']).to_pylist()
    cached = score.csvrows(rank.SOURCE/'evaluation_relations.csv')
    rel = lambda row: (row['related_instance_id'],row['experience_instance_id'])
    assert set(map(rel,relation)) == set(map(rel,cached))
    expected = {}
    for name in tables[1:]:
        for row in pq.read_table(data/(name+'.parquet'),columns=['instance_id','repo']).to_pylist():
            expected.setdefault(row['instance_id'],row['repo'])
    official_order = list(expected.items())
    fetched_order = [(r['instance_id'],r['repo']) for r in score.csvrows(rank.SOURCE/'per_query.csv')]
    assert official_order == fetched_order
    for row in score.csvrows(rank.SOURCE/'evaluation_library.csv'):
        path = data/'traces'/(row['trace_key']+'.jsonl')
        assert rank.sha(path)==pinned[row['trace_key']]
        with path.open(encoding='utf8') as stream:
            for line in stream:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                content = msg.get('message',{}).get('content')
                if msg.get('type')=='user' and isinstance(content,str) and 'problem_statement:' in content:
                    assert re.search(r'(?m)^\s*instance_id:\s*(\S+)',content)[1] == row['instance_id']
                    break
            else:
                raise AssertionError(row['trace_key'])
    reproduced={}
    with tempfile.TemporaryDirectory(dir=local) as folder:
        temp = Path(folder)
        for file in ('PROTOCOL.md','rank.py','score.py'):
            shutil.copyfile(local/file,temp/file)
        rank.HERE = score.HERE = temp
        rank.main()
        score.main()
        for name in ('registration.json','graph.json','predictions.jsonl','per_query.csv','scores.json','repositories.json'):
            reproduced[name]=rank.sha(temp/name)
            assert reproduced[name] == rank.sha(local/name)
    rank.HERE = score.HERE = local
    rank.save(local/'replication.json',{'signed_public_parquet':receipts,'reproduced':reproduced,'trace_files_checked':300,'ordinal_metadata_checked':len(official_order),'relationship_set_size':len(set(map(rel,relation)))})
    print('Original metadata and deterministic output SHA-256 checks passed.')


if __name__ == '__main__':
    main()
