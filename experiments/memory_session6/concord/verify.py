"""Standalone check of raw answers, saved judge verdicts, native receipt reuse and paired totals. Standard library only."""
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import re
import string

ROOT=Path(__file__).resolve().parent


def read(name):
    p=ROOT/name
    return json.loads(gzip.decompress(p.read_bytes()) if name.endswith('.gz') else p.read_bytes())


def evaluate(answer, gold):
    def tok(s):
        return re.sub(r'\b(a|the|an)\b',' ',(s or '').lower().translate(str.maketrans('','',string.punctuation))).split()
    a,b=tok(answer),tok(gold)
    common=(Counter(a)&Counter(b)).total()
    return int(a==b), 2*common/(len(a)+len(b)) if a or b else 1.


def close(a,b):
    return abs(a-b)<1e-9


if __name__=='__main__':
    source=read('published_projection.json.gz')
    public=read('published_results.json')
    by=defaultdict(list)
    for r in source:
        em,f1=evaluate(r['answer'],r['gold'])
        assert close(f1,r['f1']) and em==r['em']
        by[r['actor'],r['arm']].append(r)
    assert len(source)==600 and len(by)==15
    for (actor,arm),rows in by.items():
        assert len(set(r['id'] for r in rows))==len(rows)==40
        z=public[actor]['arms'][arm]
        assert z['em']==sum(r['em'] for r in rows)
        assert close(z['f1'],sum(r['f1'] for r in rows)/40)
        assert z['published_judge_correct']==sum(r['judge_correct'] for r in rows)
    if not (ROOT/'local_projection.json.gz').exists():
        raise SystemExit('Verified all 600 published answers; local_projection.json.gz is required for full verification.')
    local=read('local_projection.json.gz')
    results=read('local_results.json')
    calls=read('call_projection.json.gz')['used']
    z=defaultdict(dict);logical=0
    for r in local:
        em,f1=evaluate(r['answer'],r['gold'])
        assert em==r['em'] and close(f1,r['f1'])
        assert r['id'] not in z[r['arm']]
        z[r['arm']][r['id']]=r;logical+=len(r['requests'])
        rc=[calls[k] for k in r['requests']]
        assert sum(c is None for c in rc)==r['missing_receipt']
        assert sum(c is None or c['prompt'] is None for c in rc)==r['missing_usage']
        for k in ['prompt','completion','cached_prompt','window_presentations','window_request']:
            assert sum(c[k] or 0 for c in rc if c is not None)==r[k]
    assert len(local)==120 and len(z)==3
    assert len({s for rows in z.values() for s in rows})==40
    for arm,rows in z.items():
        assert len(rows)==40
        report=results['arms'][arm]
        assert report['em']==sum(r['em'] for r in rows.values())
        assert close(report['f1'],sum(r['f1'] for r in rows.values())/40)
    for contrast,r in results['pairs'].items():
        a,b=contrast.split('_minus_')
        ids=sorted(z[a]);d=[z[a][i]['em']-z[b][i]['em'] for i in ids]
        assert (d.count(1),d.count(-1),d.count(0))==(r['em']['wins'],r['em']['losses'],r['em']['ties'])
        assert close(sum(d)/len(d),r['em']['delta'])
        assert sum(z[a][i]['requests']==z[b][i]['requests'] for i in ids)==r['same_request_sequence_cases']
    c=results['cache']
    assert c['logical_attempts']==logical
    assert c['unique_request_keys']==len(calls)
    assert logical-len(calls)==sum(c[k] for k in ['repeated_in_same_trajectory','repeated_across_arms_within_case','repeated_across_cases'])
    print('PASS 600 author rows, 120 local trials, all exact and F1 scores, costs, pairings and cache counts')
