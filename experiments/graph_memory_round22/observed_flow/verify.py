"""Rejoin all released read references by native entity and verify the immutable files."""
from collections import Counter, defaultdict
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re

from sources import C, D, dump, read, sha


def check_reference():
    ledger = read(D / 'corpus-audit.json')
    label = {r['trace']: r['reads'] for r in read(C / 'flow-gold.json')}
    packets = {r['trace']: r for r in read(C / 'flow-packets.json')}
    forecasts = json.loads(gzip.decompress((D / 'predictions.json.gz').read_bytes()))
    time_rows = json.loads(gzip.decompress((D / 'time-query-outcomes.json.gz').read_bytes()))
    sealed = {r['trace']: r for r in forecasts}
    expected_time = {}
    counters = Counter()
    held = Counter()
    sources = read(D / 'source-lock.json')
    for src in sources:
        raw = (C / (src['git_blob'] + '.json')).read_bytes()
        assert sha(raw) == src['sha256']
        assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\x00' + raw).hexdigest() == src['git_blob']
    for entry in ledger:
        if entry['status'] != 'eligible':
            continue
        tr = entry['trace']
        native = read(C / (entry['blob'] + '.json'))
        producers = defaultdict(set)
        for ed in native['wasGeneratedBy'].values():
            m = re.fullmatch(r'(?:\w+:)?p(\d+)', ed.get('prov:activity', ''))
            if m:
                producers[ed['prov:entity']].add(int(m.group(1)))
        links = set()
        for ed in native['used'].values():
            entity = ed['prov:entity']
            m = re.fullmatch(r'(?:\w+:)?p(\d+)', ed.get('prov:activity', ''))
            if len(producers[entity]) == 1 and m:
                p = next(iter(producers[entity]))
                sig = hashlib.sha256(('entity\0' + tr + entity).encode()).hexdigest()[:24]
                links.add((sig,p,int(m.group(1))))
        cards = {r['id']: r for r in packets[tr]['cards']}
        preds = {r['id']: r for r in sealed[tr]['cards']}
        writers = defaultdict(set)
        for event in packets[tr]['events']:
            for token, _, _ in event['write']:
                writers[token].add(event['id'])
        event_ids = [r['id'] for r in packets[tr]['events']]
        assert len(event_ids) == len(set(event_ids)) and event_ids == sorted(event_ids)
        for item in label[tr]:
            n = item['consumer']; producer = item['producer']; card = item['card']
            assert (item['entity'],producer,n) in links
            expected_time[tr,card] = producer
            v=cards[card]['base'][0]
            prefix = {j for j in writers[v] if j<n}
            pred = preds[card]
            assert producer in prefix and set(pred['arms']['universal']) == prefix
            assert pred['before'] == len(prefix) and pred['final'] == len(writers[v])
            if len(prefix)==1 and len(writers[v])>1:
                assert pred['arms']['append']==[producer] and not pred['arms']['retract']
                counters['dropped_valid_edges']+=1
            if entry['family']!='case/pplant':
                held['reads']+=1
                held['exactly_one_at_read']+=int(len(prefix)==1)
                held['exactly_one_final']+=int(len(writers[v])==1)
                held['last_writer_by_value_correct']+=int(producer==max(prefix))
            counters['rejoined_versioned_reads']+=1
        assert len(packets[tr]['cards'])==len(label[tr])
        counters['activities']+=len(event_ids)
    for z in time_rows:
        a,b = expected_time[z['trace'],z['first']], expected_time[z['trace'],z['next']]
        assert z['real_producers']==[a,b]
        assert z['truth']==[a==z['producer'],b==z['producer']]
        counters['paired_reads']+=1
        counters['unequal_target_answers']+=int(z['truth'][0]!=z['truth'][1])
    assert counters == {'rejoined_versioned_reads':1804,'dropped_valid_edges':155,'activities':3673,
                        'paired_reads':1348,'unequal_target_answers':298}
    check = {'verified':counters, 'without_case_pplant':held, 'source_artifacts':len(sources)}
    dump(D/'audit.json',check)
    return check


def manifest():
    return {p.name:sha(p.read_bytes()) for p in sorted(D.iterdir()) if p.is_file() and p.name!='MANIFEST_SHA256.json'}


if __name__ == '__main__':
    arg = argparse.ArgumentParser()
    arg.add_argument('--seal',action='store_true')
    options=arg.parse_args()
    print(check_reference())
    lock=D/'MANIFEST_SHA256.json'
    if options.seal:
        dump(lock,manifest())
    else:
        assert manifest() == read(lock)
    print('Manifest files:',len(read(lock)),'sha256:',sha(lock.read_bytes()))

