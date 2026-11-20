"""Compile records from prior public interactions. No target labels or patches are read."""
import collections
import hashlib
import json
import os
import re
from pathlib import Path

import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('SWE_CONTEXT_DATA', 'D:/CodexResearch/x20-swe-context'))


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding='utf-8')


def mask(text):
    text = re.sub(r'https?://\S+|\b[\w.-]+__[\w.-]+-\d+\b|\B#\d+\b|\b[0-9a-fA-F]{32,64}\b', ' ', text)
    text = re.sub(r'\b(?:PR|issue|pull[ -]request|ticket|GH|bug|changeset)\s*[-:#]?\s*\d{2,}\b', ' ', text, flags=re.I)
    text = re.sub(r'\b(?:pulls?|issues?|tickets?)/\d+\b|\b(?:commit|revision|changeset)\s+[0-9a-f]{7,40}\b', ' ', text, flags=re.I)
    return ' '.join(text.split())


def clip(text, n, tail=0):
    words = text.split()
    return ' '.join(words[:n-tail] + words[-tail:]) if len(words) > n and tail else ' '.join(words[:n])


def load_card(path):
    issue = ''
    closure = ''
    paths, identifiers = [], collections.Counter()
    for line in path.open(encoding='utf-8'):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            print('Malformed upstream JSONL row skipped',path.name,len(line))
            continue
        content = row.get('message', {}).get('content')
        if row.get('type') == 'user' and isinstance(content, str) and not issue:
            if 'problem_statement:' in content:
                issue = content.split('problem_statement:', 1)[1]
                issue = re.split(r'(?m)^\s{0,4}(?:base_commit|FAIL_TO_PASS|PASS_TO_PASS|patch|test_patch|created_at|hints_text|environment_setup_commit|instance_id|version):', issue)[0]
            continue
        if row.get('type') != 'assistant':
            continue
        if isinstance(content, str):
            closure = content
            continue
        for item in content or []:
            if item.get('type') == 'text' and item.get('text','').strip():
                closure = item['text']
            if item.get('type') != 'tool_use' or item.get('name') not in {'Edit','MultiEdit','Write'}:
                continue
            arg = item.get('input', {})
            path_text = arg.get('file_path','').replace('\\','/').split('/testbed/')[-1]
            path_text = '/'.join(path_text.split('/')[-4:]).strip('./')
            if path_text and path_text not in paths:
                paths.append(path_text)
            for change in arg.get('edits', [arg]):
                snippet = change.get('new_string', change.get('content', ''))[:4500]
                for name in set(re.findall(r'\b[A-Za-z_]\w{2,}\b', snippet)):
                    if '_' in name or re.search(r'[a-z][A-Z]', name) or name[:1].isupper():
                        identifiers[name] += 1
    evidence = paths + [i for i,_ in sorted(identifiers.items(), key=lambda kv:(-kv[1],kv[0]))]
    return {'key':path.stem, 'symptom':clip(mask(issue),210,35), 'closure':clip(mask(closure),135), 'edits':clip(mask(' '.join(evidence)),85)}


if __name__ == '__main__':
    cards = [load_card(p) for p in sorted((DATA/'traces').glob('*.jsonl'))]
    assert len(cards) == 300
    write('cards.json', cards)
    queries = []
    seen = set()
    for name,group in [('SWEContextBench_Related_Lite','lite'),('SWEContextBench_Related','extension')]:
        for row in pq.read_table(DATA/(name+'.parquet'), columns=['instance_id','problem_statement']).to_pylist():
            if row['instance_id'] in seen:
                continue
            seen.add(row['instance_id'])
            queries.append({'ordinal':len(queries),'group':group, 'query':clip(mask(row['problem_statement']),280,60)})
    write('queries.json', queries)
    print(len(cards),collections.Counter(q['group'] for q in queries), {f:sum(bool(c[f]) for c in cards) for f in ['symptom','closure','edits']})

