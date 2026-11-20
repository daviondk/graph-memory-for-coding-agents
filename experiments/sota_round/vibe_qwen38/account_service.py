"""Reconcile native receipts with the four local model experiments and incomplete work."""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import csv
import hashlib
import json


def j(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def lines(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('root',type=Path,help='Root containing swe_context, vibe and vibe_qwen38')
    args=cli.parse_args();root=args.root
    dest=root/'vibe_qwen38';path=dest/'requests.jsonl'
    events=lines(path)
    ok={e['id']:e for e in events if e['http_status']==200}
    assert len(ok)==sum(e['http_status']==200 for e in events)
    assigned={}

    def mark(group,key,expect=None):
        assert key in ok and key not in assigned
        if expect:
            u=ok[key]['usage']
            assert all(u[t]==int(expect[t]) for t in ('prompt_tokens','completion_tokens'))
        assigned[key]=group

    for phase in ('qwen38_27b','in_loop'):
        with (root/'vibe'/phase/'episode_calls.csv').open(encoding='utf8',newline='') as f:
            for row in csv.DictReader(f):mark('Vibe '+phase,row['response_id'],row)
    for key in j(root/'vibe/qwen38_27b/interruption_accounting.json')['interrupted_response_ids']:
        mark('Vibe interrupted',key)
    for row in lines(root/'swe_context/matched_reader/calls.jsonl'):
        mark('SWE '+row['arm'],row['response_id'],row['usage'])
    primary=sorted((e for k,e in ok.items() if k not in assigned and e['max_output']==12 and not e['tool_names']),key=lambda x:x['epoch'])
    statements=lines(root/'swe_context/qwen_calls.jsonl')
    assert len(primary)==len(statements)==99 and [s['ordinal'] for s in statements]==list(range(99))
    for e,row in zip(primary,statements):mark('SWE primary',e['id'],row['usage'])
    extra=[e for k,e in ok.items() if k not in assigned]
    first=min(e['epoch'] for k,e in ok.items() if assigned.get(k)=='Vibe qwen38_27b')
    assert len(extra)==5 and all(e['epoch']<first for e in extra)
    for e in extra:mark('pre-study tool smokes',e['id'])
    total=defaultdict(Counter)
    for key,group in assigned.items():
        u=ok[key]['usage'];v=total[group];v['calls']+=1;v['input']+=u['prompt_tokens'];v['output']+=u['completion_tokens']
    summary={'all_logged_requests':len(events),'successful_native_calls':len(ok),'http_failures':len(events)-len(ok),
             'grouped':total,'total':sum(total.values(),Counter()),'request_log_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
             'primary_matching':'99 residual no-tool 12-token-limit requests, sequence/each token count checked against frozen calls. Other post-study controls matched by native response ID.'}
    (dest/'full_service_accounting.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()
