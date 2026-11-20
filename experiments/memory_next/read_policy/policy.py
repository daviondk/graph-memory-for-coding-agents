"""Prospective read gate using only exposed issue/card text and unlabeled base rankings."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parents[1] / 'sota_round' / 'swe_context'
INPUTS = ('cards.json', 'queries.json', 'blind_ranks.json')
WORD = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
STOP = set('true false none null init self cls class def return pass else elif import from with test tests src source python file files path docs setup lib core main base args kwargs'.split())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(path.read_text(encoding='utf8'))


def save(path, obj):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=1)+'\n', encoding='utf8')
    temporary.replace(path)


def terms(text):
    return {t for t in map(str.casefold, WORD.findall(text)) if len(t) >= 4 and t not in STOP and any('a' <= c <= 'z' for c in t)}


def cap(text, size):
    return ' '.join(text.split()[:size])


def record_signature(cards):
    by_term = defaultdict(set)
    for c in cards:
        for t in terms(cap(c['edits'], 40)):
            by_term[t].add(c['key'])
    return {k: sorted(v) for k,v in sorted(by_term.items()) if len(v)*100 <= 15*len(cards)}


def make_assignment(row, slate, postings, short_tokens):
    keys=set(slate)
    evidence=[]
    for term in sorted(terms(row['query'])):
        edit_owners=keys.intersection(postings.get(term, []))
        if len(edit_owners)!=1:
            continue
        short_owners={k for k in slate if term in short_tokens[k]}
        if short_owners != edit_owners:
            evidence.append({'term':term,'edit_owner':next(iter(edit_owners)),'short_owners':sorted(short_owners)})
    return {'ordinal':row['ordinal'], 'slate':slate, 'full':bool(evidence), 'distinctive_signals':evidence}


def register(parent):
    if (HERE/'registration.json').exists():
        raise FileExistsError('Existing registration must be kept')
    save(HERE/'registration.json',{'utc':stamp(), 'protocol':sha(HERE/'PROTOCOL.md'), 'policy':sha(HERE/'policy.py'), 'inputs':{n:sha(parent/n) for n in INPUTS}})


def assign(parent):
    registration=load(HERE/'registration.json')
    assert registration['protocol']==sha(HERE/'PROTOCOL.md') and registration['policy']==sha(HERE/'policy.py')
    for name, h in registration['inputs'].items():
        assert sha(parent/name)==h
    start=time.perf_counter()
    cards=load(parent/'cards.json')
    queries=load(parent/'queries.json')[:99]
    ranks=load(parent/'blind_ranks.json')
    assert len(cards)==len({r['key'] for r in cards})==300
    assert len(queries)==99 and all(r['group']=='lite' and r['ordinal']==i for i,r in enumerate(queries))
    t1=time.perf_counter()
    postings=record_signature(cards)
    short={r['key']:terms(cap(r['symptom'],175)+' '+cap(r['closure'],90)) for r in cards}
    t2=time.perf_counter()
    rows=[]
    for q,r in zip(queries,ranks):
        assert q['ordinal']==r['ordinal'] and len(set(r['fusion'][:5]))==5
        rows.append(make_assignment(q,r['fusion'][:5],postings,short))
    t3=time.perf_counter()
    k=sum(r['full'] for r in rows)
    selected=set(sorted(range(len(rows)),key=lambda n:hashlib.sha256(('read-policy-null-v1|'+str(n)).encode()).hexdigest())[:k])
    for r in rows:
        r['random_full']=r['ordinal'] in selected
    # Compare the raw byte cost of a deployable, minified postings schema.
    index=(json.dumps(postings,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    if (HERE/'decision_lock.json').exists():
        assert (HERE/'postings.json').read_bytes()==index and rows==load(HERE/'assignments.json')
        return
    (HERE/'postings.json').write_bytes(index)
    save(HERE/'assignments.json',rows)
    save(HERE/'decision_lock.json',{'utc':stamp(),'source_registration':sha(HERE/'registration.json'),'rows':99,'n_full':k,
       'assignments':sha(HERE/'assignments.json'),'index':sha(HERE/'postings.json'),'postings_bytes':len(index),
       'tokens_indexed':len(postings),'postings':sum(map(len,postings.values())), 'card_count':len(cards),
       'load_seconds':t1-start,'index_and_short_text_preparation_seconds':t2-t1,'gate_99_seconds':t3-t2,'python':sys.version})
    print('locked',len(rows),'assignments;',k,'full;',len(index),'index bytes')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['register','assign'])
    p.add_argument('--parent',type=Path,default=ARCHIVE)
    a=p.parse_args()
    (register if a.mode=='register' else assign)(a.parent)

