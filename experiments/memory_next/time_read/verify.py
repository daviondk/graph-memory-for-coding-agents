"""Offline verification using dated identifiers and public truth saved by the chronology audit."""
import csv
import json
import hashlib
import re
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TRANSFER=ROOT.parent/'transfer'

def j(n):return json.loads((ROOT/n).read_text(encoding='utf8'))
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def verify():
    for n,h in j('end_lock.json').items():
        assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n
    src={x['trace_key']:x for x in rows(TRANSFER/'source_times_lite.csv')}
    targets=rows(TRANSFER/'query_times_lite.csv')
    gold={int(x['ordinal']):x['gold'].split('|') for x in rows(TRANSFER/'lite_chronology.csv')}
    cases=rows(ROOT/'per_query.csv')
    actual={}
    for line in (ROOT/'calls.jsonl').read_text(encoding='utf8').splitlines():
        r=json.loads(line)
        assert r['payload_sha256'] not in actual
        actual[r['payload_sha256']]=r
    choices={(x['ordinal'],x['arm']):x for x in j('blind_decisions.json')}
    stats=Counter()
    for x,t,c in zip(j('blind_lists.json'),targets,cases,strict=True):
        i=x['ordinal']
        assert int(c['ordinal'])==int(t['ordinal'])==i
        pool={k for k,v in src.items() if t['opening_complete']=='1' and v['repo'].lower()==t['repo'].lower() and v['source_pr']!=t['target_pr'] and v['source_merge'] and v['source_merge']<t['cutoff_utc']}
        assert pool==set(x['eligible'])
        hits=lambda key:bool(key and src[key]['instance_id'] in gold[i])
        assert sum(hits(k) for k in pool)==int(c['linked']),(i,gold[i],c)
        for m,rank in x['ranks'].items():
            assert len(rank)==len(pool)==len(set(rank)) and set(rank)==pool
            for k in [1,5]:
                col=f'{m}_{k}'
                a=int(any(hits(key) for key in rank[:k]))
                assert a==int(c[col])
                stats[col]+=a
            if (i,m) in choices:
                decision=choices[i,m]
                key=rank[0] if rank else None
                if len(rank)>1:
                    r=actual[decision['payload_sha256']]
                    assert set(r['order'])==set(rank[:5])
                    match=re.fullmatch(r'\s*([1-5])[.)]?\s*',r['raw'] or '')
                    valid=bool(match and int(match[1])<=len(r['order']))
                    assert valid==decision['valid']
                    if valid:key=r['order'][int(match[1])-1]
                assert key==decision['choice']
                assert int(c[m+'_qwen'])==int(hits(key))
                stats[m+'_qwen']+=int(hits(key))
                stats[m+'_qwen_last']+=int(bool(key and src[key]['instance_id']==gold[i][-1]))
    summary=j('results.json')
    assert dict(stats)==summary['all']['hits']
    assert len(cases)==99 and len(choices)==198 and len(actual)==summary['costs']['actual_calls']
    print('Verified all 99 dated pools, eight permutations each, 198 reader decisions, actual API records and aggregate scores.')
if __name__=='__main__':verify()

