"""Blind ranker. No outcome file or issue–experience mapping is read here."""
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
SOURCE = WORK / 'sota_round' / 'swe_context'
TIME = WORK / 'memory_next' / 'time_read'
TOKEN = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?')
TECH = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
STOP = set('instance_id model_patch test_patch model_name_or_path problem_statement fail_to_pass pass_to_pass base_commit created_at output_file get_file testbed traceback stdout stderr'.split())
ARMS = ('base', 'direct', 'neighbors', 'graph', 'permutation')


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1), encoding='utf8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_pins():
    blind = read(SOURCE / 'blind_commit.json')
    for filename in ('cards.json', 'queries.json', 'blind_ranks.json'):
        assert sha(SOURCE / filename) == blind[filename]
    name = 'recall_hybrid.json'
    assert sha(SOURCE / name) == read(SOURCE / 'recall_hybrid_pin.json')['sha256'][name]


def anchors(text):
    out = set()
    for term in text.split():
        key = term.lower()
        if any(c.isdigit() for c in key) or '__' in key or key in STOP:
            continue
        if '/' in key or '.' in key:
            if any(s in key for s in ('swebench', 'preds.json', '/output/', '.log', '.patch', '/tmp/')):
                continue
            base = key.rsplit('/', 1)[-1]
            if re.fullmatch(r'[a-z_][a-z_.-]*\.[a-z]+', base):
                out.add('p/' + base)
        elif TECH.fullmatch(term) and ('_' in term or re.search(r'[a-z][A-Z]', term)):
            out.add('i/' + key)
    return out


def query_anchors(text):
    out = set()
    for name in TOKEN.findall(text):
        lower = name.lower()
        out.add('p/' + lower)
        for part in lower.split('.'):
            out.add('i/' + part)
    return out


def normalize(values):
    maximum = max(values, default=0)
    return [v / maximum if maximum else 0.0 for v in values]


def channels(shortlist, edges, weight, query):
    """Produce per-record direct witness mass and corroboration from other seeds."""
    direct, support, why = [], [], []
    for doc in shortlist:
        matched = sorted(query & edges[doc])
        direct.append(math.fsum(weight[e] for e in matched))
        pieces = []
        peer_evidence = []
        for rank, peer in enumerate(shortlist[:5], 1):
            if peer == doc:
                continue
            shared = sorted(edges[peer] & edges[doc])
            if not shared:
                continue
            denominator = math.fsum(weight[e] for e in sorted(edges[peer] | edges[doc]))
            numerator = math.fsum(weight[e] for e in shared)
            contribution = numerator / (denominator * rank) if denominator else 0.0
            pieces.append(contribution)
            peer_evidence.append((contribution, peer, shared))
        support.append(math.fsum(pieces))
        why.append({'direct_anchors': matched, 'peer': max(peer_evidence, default=(0, None, []))})
    return normalize(direct), normalize(support), why


def one_query(shortlist, eligible, graph, query):
    known = {d: graph[d] for d in eligible}
    n = len(known)
    df = Counter(e for values in known.values() for e in values)
    weight = {e: math.log((n + 1) / (f + 1)) for e, f in df.items()}
    a, b, why = channels(shortlist, known, weight, query)
    perm_order = sorted(eligible, key=lambda d: hashlib.sha256(('placebo|20261118|' + d).encode()).digest())
    perm = {d: known[peer] for d, peer in zip(perm_order, perm_order[1:] + perm_order[:1])}
    c, e, _ = channels(shortlist, perm, weight, query)
    arms = {'base': [0.0] * len(shortlist), 'direct': a, 'neighbors': b,
            'graph': [0.65 * x + 0.35 * y for x, y in zip(a, b)],
            'permutation': [0.65 * x + 0.35 * y for x, y in zip(c, e)]}
    ranks = {}
    for name, bonuses in arms.items():
        scores = [-math.log(r) + math.log(3) * bonus for r, bonus in enumerate(bonuses, 1)]
        ranks[name] = [shortlist[i] for i in sorted(range(len(scores)), key=lambda i: (-scores[i], i))]
        assert sorted(ranks[name]) == sorted(shortlist)
    chosen = ranks['graph'][:1]
    witness = None
    if chosen:
        idx = shortlist.index(chosen[0])
        witness = {**why[idx], 'doc': chosen[0], 'base_rank': idx + 1, 'A': a[idx], 'B': b[idx]}
    return {'ranks': ranks, 'n_permitted': n,
            'permitted_sha256': hashlib.sha256('|'.join(sorted(eligible)).encode()).hexdigest(),
            'direct_positive': any(a), 'neighbor_positive': any(b), 'witness': witness}


def main():
    start = time.perf_counter()
    verify_pins()
    cards = read(SOURCE / 'cards.json')
    query_rows = read(SOURCE / 'queries.json')
    first = read(SOURCE / 'blind_ranks.json')
    recall = read(SOURCE / 'recall_hybrid.json')
    time_lists = read(TIME / 'blind_lists.json')
    graph = {d['key']: anchors(d['edits']) for d in cards}
    assert len(graph) == 300
    assert [d['ordinal'] for d in first] == [d['ordinal'] for d in query_rows] == list(range(357))
    assert [d['ordinal'] for d in recall] == [d['ordinal'] for d in time_lists] == list(range(99))
    save(HERE / 'graph.json', {d: sorted(nodes) for d, nodes in graph.items()})
    inputs = [SOURCE / f for f in ('cards.json','queries.json','blind_ranks.json','recall_hybrid.json')]
    inputs.append(TIME / 'blind_lists.json')
    save(HERE / 'registration.json', {'inputs': {str(p): sha(p) for p in inputs}, 'protocol': sha(HERE/'PROTOCOL.md'), 'code': sha(HERE/'rank.py')})
    path = HERE / 'predictions.jsonl'
    setups = Counter()
    with path.open('w', encoding='utf8', newline='\n') as out:
        for i, row in enumerate(query_rows):
            sets = [('fusion_lite' if i < 99 else 'fusion_extension', first[i]['fusion'], list(graph))]
            if i < 99:
                sets.append(('recall_lite', recall[i]['recall_hybrid'], list(graph)))
                hist = time_lists[i]
                sets.append(('online_lite', hist['ranks']['online_fields'][:10], hist['eligible']))
            for key, shortlist, eligible in sets:
                assert len(shortlist) == min(10, len(eligible)) and set(shortlist) <= set(eligible)
                entry = one_query(shortlist, eligible, graph, query_anchors(row['query']))
                out.write(json.dumps({'ordinal': i, 'setup': key, **entry}, sort_keys=True) + '\n')
                setups[key] += 1
    entities = set.union(*graph.values())
    save(HERE / 'prediction_lock.json', {'registration':sha(HERE/'registration.json'),'graph':sha(HERE/'graph.json'),
         'predictions':sha(path),'seconds':time.perf_counter()-start,'python':sys.version,'setups':dict(setups),
         'vertices':len(graph)+len(entities),'sessions_with_edges':sum(bool(v) for v in graph.values()),
         'anchor_nodes':len(entities),'edges':sum(map(len,graph.values())), 'path_nodes':sum(s.startswith('p/') for s in entities)})
    print(json.dumps(read(HERE / 'prediction_lock.json')))


if __name__ == '__main__':
    main()
