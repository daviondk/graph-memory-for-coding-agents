"""Open labels only after validating the immutable predictions and recompute all outcomes."""
import csv
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from rank import ARMS, HERE, SOURCE, TIME, read, save, sha

def csvrows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def pair(rows, arm, reference):
    changes = defaultdict(list)
    for d in rows:
        changes[d['repo']].append(int(d[arm] == 1) - int(d[reference] == 1))
    diffs = [delta for values in changes.values() for delta in values]
    wins, losses = diffs.count(1), diffs.count(-1)
    p = min(1.0, 2.0 * sum(math.comb(wins+losses, i) for i in range(min(wins,losses)+1)) / 2**(wins+losses))
    clusters = [(sum(v),len(v)) for k,v in sorted(changes.items())]
    rng = random.Random(20261118)
    boot = []
    for _ in range(10000):
        sample = rng.choices(clusters, k=len(clusters))
        boot.append(sum(x for x,_ in sample)/sum(y for _,y in sample))
    boot.sort()
    return {'wins':wins,'losses':losses,'delta':statistics.mean(diffs),'ci95_repo':[boot[250],boot[9749]],'n_repos':len(clusters),'p_exact_descriptive':p}

def describe(items):
    methods = {}
    for arm in ARMS:
        positions = [item[arm] for item in items]
        methods[arm] = {f'Hit@{k}':sum(0 < pos <= k for pos in positions) for k in [1,5,10]}
        methods[arm]['MRR@10'] = statistics.mean((1/p if p else 0.0) for p in positions)
    return {'n':len(items), 'n_gold_available':sum(x['available'] for x in items),
            'query_anchor':sum(x['direct_positive'] for x in items), 'neighbor_anchor':sum(x['neighbor_positive'] for x in items),
            'changed_top':sum(x['changed_top'] for x in items), 'methods':methods,
            'comparisons':{x:pair(items,'graph',x) for x in ARMS if x != 'graph'}}


def main():
    lock = read(HERE/'prediction_lock.json')
    assert lock['predictions'] == sha(HERE/'predictions.jsonl') and lock['graph'] == sha(HERE/'graph.json')
    assert lock['registration'] == sha(HERE/'registration.json')
    reg = read(HERE/'registration.json')
    for path, expected in reg['inputs'].items():
        assert sha(Path(path)) == expected
    assert reg['protocol'] == sha(HERE/'PROTOCOL.md') and reg['code'] == sha(HERE/'rank.py')
    gold = defaultdict(set)
    for row in csvrows(SOURCE / 'evaluation_relations.csv'):
        gold[row['related_instance_id']].add(row['experience_instance_id'])
    library = {r['trace_key']:r['instance_id'] for r in csvrows(SOURCE / 'evaluation_library.csv')}
    assert set(library) == set(read(HERE/'graph.json'))
    frozen_reference = csvrows(SOURCE / 'per_query.csv')
    meta = {int(r['ordinal']):(r['instance_id'],r['repo']) for r in frozen_reference}
    online = {r['ordinal']:r['eligible'] for r in read(TIME/'blind_lists.json')}
    time_inputs = TIME.parent/'transfer'
    src_times = {r['trace_key']:r for r in csvrows(time_inputs/'source_times_lite.csv')}
    q_times = {int(r['ordinal']):r for r in csvrows(time_inputs/'query_times_lite.csv')}
    for i, pool in online.items():
        q = q_times[i]
        assert set(pool) == {k for k, s in src_times.items() if s['source_merge'] and s['source_merge'] < q['cutoff_utc'] and s['repo'].lower()==q['repo'].lower() and s['instance_id'] != q['target'] }
    inputs = [SOURCE/k for k in ['evaluation_relations.csv','evaluation_library.csv','per_query.csv']]
    inputs += [time_inputs/k for k in ['source_times_lite.csv','query_times_lite.csv']]
    per_query = []
    for line in (HERE/'predictions.jsonl').read_text(encoding='utf8').splitlines():
        pred = json.loads(line)
        i, setup, ranks = pred['ordinal'], pred['setup'], pred['ranks']
        target, repo = meta[i]
        allowed = online[i] if setup == 'online_lite' else library.keys()
        labels = gold[target]
        assert labels
        row = {'setup':setup,'ordinal':i,'instance_id':target,'repo':repo,'available':int(any(library[k] in labels for k in allowed)),
               'direct_positive':int(pred['direct_positive']), 'neighbor_positive':int(pred['neighbor_positive']),
               'changed_top':int(ranks['base'][:1] != ranks['graph'][:1]),'gold_ids':'|'.join(sorted(labels)),
               'base_top':next(iter(ranks['base']),''),'graph_top':next(iter(ranks['graph']),'')}
        for arm in ARMS:
            row[arm] = next((r for r,d in enumerate(ranks[arm],1) if library[d] in labels),0)
        if setup in {'fusion_lite','fusion_extension','recall_lite'}:
            ref = 'recall_hybrid_1' if setup=='recall_lite' else 'fusion_1'
            assert int(row['base']==1) == int(frozen_reference[i][ref])
        per_query.append(row)
    dest=HERE/'per_query.csv'
    with dest.open('w',newline='',encoding='utf8') as out:
        writer=csv.DictWriter(out,list(per_query[0]))
        writer.writeheader()
        writer.writerows(per_query)
    groups = defaultdict(list)
    for r in per_query:
        groups[r['setup']].append(r)
        if r['available'] and r['setup'] in {'fusion_extension','online_lite'}:
            groups[r['setup']+'_available'].append(r)
    summary={g:describe(rows) for g,rows in groups.items()}
    save(HERE/'scores.json',summary)
    by_repo=[]
    for k,rows in groups.items():
        for repo in sorted({r['repo'] for r in rows}):
            members=[r for r in rows if r['repo']==repo]
            by_repo.append({'setup':k,'repo':repo,'n':len(members), **{m: sum(r[m]==1 for r in members) for m in ARMS}})
    save(HERE/'repositories.json',by_repo)
    resultfiles=['per_query.csv','scores.json','repositories.json','score.py','prediction_lock.json']
    save(HERE/'evaluation_lock.json',{'labels_and_metadata':{str(p):sha(p) for p in inputs},'scored':{n:sha(HERE/n) for n in resultfiles}})
    for k,v in summary.items():
        print(k,v['n'],v['n_gold_available'],[v['methods'][m]['Hit@1'] for m in ARMS],v['comparisons']['base'])


if __name__ == '__main__':
    main()
