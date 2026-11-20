"""Portable independent check, Python standard library only. Run from any directory."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import math
import re
import string

ROOT=Path(__file__).resolve().parent


def read(name):
    p=ROOT/name
    buf=p.read_bytes()
    return json.loads(gzip.decompress(buf) if p.suffix=='.gz' else buf)


def scores(a,b):
    def tokens(t):
        s=''.join(ch for ch in (t or '').lower() if ch not in string.punctuation)
        return re.sub(r'\b(a|an|the)\b',' ',s).split()
    x,y=tokens(a),tokens(b)
    n=sum((Counter(x)&Counter(y)).values())
    return int(x==y),2*n/(len(x)+len(y)) if x or y else 1.


def main():
    rows=read('projection.json.gz');index=read('receipt_projection.json.gz')
    results=read('results.json');locked=read('decision_lock.json');design=read('design_lock.json')
    judge=read('answers_for_judge.json')
    for f,h in design['sha256'].items():
        assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h
    z={(r['id'],r['arm']):r for r in rows};ids=design['roster']
    assert len(z)==len(rows)==120 and len(ids)==len(set(ids))==40
    assert len({(r['id'],r['arm']) for r in judge})==len(judge)==len(locked)==80
    assert all(r['arm'] in ('control','correction') and z[r['id'],r['arm']]['answer']==r['answer'] for r in judge)
    for (sid,a),r in z.items():
        em,f1=scores(r['answer'],r['gold']);assert em==r['em'] and abs(f1-r['f1'])<1e-12
        assert all(k in index and index[k]['status']==200 for k in r['requests'])
        for field in ('prompt','completion'):
            assert r[field]==sum(index[k][field] for k in r['requests'])
        if a!='baseline':
            fn=f'{sid}_{a}.json.gz';assert locked[fn]==r['sha256']
            raw=ROOT/'trials'/fn
            if raw.exists():
                assert hashlib.sha256(raw.read_bytes()).hexdigest()==locked[fn]
                d=json.loads(gzip.decompress(raw.read_bytes()))
                assert (d['id'],d['arm'],d['answer'],d['requests'])==(sid,a,r['answer'],r['requests'])
    for a in ('correction','control','baseline'):
        rs=[z[s,a] for s in ids]; m=results['arms'][a]
        for field in ('em','cues','read_file','grep','prompt','completion','cue_bytes','phrase_words'):
            assert m[field]==sum(r[field] for r in rs)
        assert math.isclose(m['f1'],sum(r['f1'] for r in rs)/40)
        assert m['cue_cases']==sum(bool(r['cues']) for r in rs)
    for key,v in results['pair'].items():
        a,b=key.split('-')
        for field in ('em','f1','cues','prompt','read_file'):
            diffs=[z[s,a][field]-z[s,b][field] for s in ids]
            assert math.isclose(v[field]['delta'],sum(diffs)/40,abs_tol=1e-12)
            assert v[field]['wins']==sum(x>1e-12 for x in diffs)
            assert v[field]['losses']==sum(x< -1e-12 for x in diffs)
    cpu=read('cpu_summary.json')
    assert cpu==design['cpu_summary'] and design['chosen']=='previous'
    if (ROOT/'cpu').exists():
        old=[read('cpu/'+s+'_replay.json.gz') for s in ids]
        assert sum(len(r['requests']) for r in old)==cpu['matched_original_request_hashes']
        for mode in ('previous','returned'):
            assert sum(bool(r['opportunities'][mode]) for r in old)==cpu['opportunity'][mode]['cases']
            assert sum(len(r['opportunities'][mode]) for r in old)==cpu['opportunity'][mode]['events']
    print('PASS: 80 locked interventions, 40 controls, 3 paired contrasts, receipts, CPU eligibility and blind-judge handoff.')


if __name__=='__main__':main()
