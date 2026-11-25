"""Decompose paired, multi-event evidence recall on sealed, fixed-budget readings."""
from collections import defaultdict
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GOLD = ROOT / 'cpu_fallback/inputs/test-gold.json.gz'
SCOPES = ('minimum_two', 'exactly_two')
ARMS = ('rgcn/prefix', 'seed/prefix', 'rgcn/related', 'rgcn/skip')
CONTRASTS = (('rgcn/prefix', 'seed/prefix'), ('rgcn/related', 'rgcn/skip'))
NAMES = ('event', 'pair', 'all', 'marginal_square', 'covariance', 'partner_given_first')

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read(path):
    b = path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix == '.gz' else b)

def put(path, obj):
    b = (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    if path.suffix == '.gz':
        b = gzip.compress(b, mtime=0)
    path.write_bytes(b)

def lock():
    assert not (HERE/'plan.json').exists()
    put(HERE/'plan.json', dict(protocol=sha(HERE/'PROTOCOL_RU.md'), code=sha(HERE/'analyze.py'),
                               gold=sha(GOLD), boot=10000, seed=261122245, arms=ARMS, scopes=SCOPES,
                               available_known=sha(ROOT/'cpu_fallback/availability/results.json'),
                               hash64_had_results=(ROOT/'cpu_fallback/hash64/results.json').exists()))

def by_field(spans):
    groups = defaultdict(list)
    for s in spans:
        key = (s['event_id'], s['json_pointer'])
        groups[key].append((s['char_start'], s['char_end']))
    result = {}
    for key, intervals in groups.items():
        merged = []
        for start, end in sorted(intervals):
            assert start < end
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        result[key] = merged
    return result

def count_complete(gold, selected):
    covered = by_field(s for n in selected for s in n['source_spans'])
    complete = {}
    for key, targets in gold.items():
        event = key[0]
        source = covered.get(key, [])
        matched = all(any(a <= start and end <= b for a, b in source) for start, end in targets)
        complete[event] = complete.get(event, True) and matched
    return sum(complete.values())

def components(x):
    event, pair, full = np.moveaxis(x, -1, 0)
    assert np.all(event > 0)
    return np.stack([event, pair, full, event**2, pair-event**2, pair/event], axis=-1)

def summarize(rows, seed, repeat):
    by_trajectory = defaultdict(lambda: np.zeros(1 + 3*len(ARMS), dtype='float64'))
    for row in rows:
        values = by_trajectory[row['t']]
        values[0] += 1
        for col, arm in enumerate(ARMS):
            k, m = row['k'][arm], row['m']
            values[1+3*col:4+3*col] += (k/m, k*(k-1)/(m*(m-1)), int(k==m))
    data = np.stack([by_trajectory[t] for t in sorted(by_trajectory)])
    def compute(s):
        return components((s[...,1:]/s[...,:1]).reshape(*s.shape[:-1], len(ARMS), 3))
    point = compute(data.sum(axis=0))
    samples = []
    rng = np.random.default_rng(seed)
    for begin in range(0, repeat, 64):
        inds = rng.integers(0, len(data), size=(min(64,repeat-begin), len(data)))
        samples.append(compute(data[inds].sum(axis=1)))
    bootstrap = np.concatenate(samples)
    contrasts = {}
    for a,b in CONTRASTS:
        i,j = ARMS.index(a), ARMS.index(b)
        delta = point[i]-point[j]
        boot = bootstrap[:,i]-bootstrap[:,j]
        assert np.allclose(boot[:,1], boot[:,3]+boot[:,4])
        interval = np.quantile(boot, (.025,.975), axis=0)
        contrasts[a+' minus '+b] = {
            name: {'difference':float(delta[v]),'ci95':interval[:,v].tolist()} for v,name in enumerate(NAMES)
        }
    return {'n':len(rows),'trajectories':len(data),'arms':{
        arm:{name:float(x) for name,x in zip(NAMES,line,strict=True)} for arm,line in zip(ARMS,point,strict=True)
    },'contrasts':contrasts}

def analyze(panel):
    plan = read(HERE/'plan.json')
    assert plan['code']==sha(HERE/'analyze.py') and plan['protocol']==sha(HERE/'PROTOCOL_RU.md')
    assert plan['gold']==sha(GOLD)
    path = ROOT if panel=='full' else ROOT/'cpu_fallback'/panel
    sealed = read(path/'forecast-seal.json')
    files = sealed['forecasts'] if panel=='full' else sealed['files']
    gold = {q:by_field(spans) for q,spans in read(GOLD).items()}
    events = {q:len({event for event,_ in fields}) for q,fields in gold.items()}
    records = {q:{'q':q, 'm':m, 'k':{}} for q,m in events.items() if m>=2}
    sources = [name for name in files if name.startswith('forecasts-') and name.endswith('.json.gz')]
    assert len(sources)==16
    for name in sorted(sources):
        assert files[name]==sha(path/name)
        method = name.split('-')[1]
        for rec in read(path/name):
            q=rec['q']
            if q not in records:
                continue
            row=records[q]
            assert row.setdefault('t',rec['t'])==rec['t']
            nodes={n['node_id']:n for n in rec['rr']}
            for arm, ids in rec['arms'].items():
                key = method+'/'+arm
                if key in ARMS:
                    assert key not in row['k']
                    selected=[nodes[k] for k in ids]
                    assert sum(s['token_count'] for s in selected)<=2048
                    row['k'][key]=count_complete(gold[q], selected)
    assert len(gold)==2000 and all(row['k'].keys()==set(ARMS) for row in records.values())
    checked = set()
    for r in read(path/'outcomes.json.gz'):
        q = r['q']
        arm = r['method']+'/'+r['arm']
        if r.get('stage','test')=='test' and q in records and arm in ARMS:
            row=records[q]
            assert (row['k'][arm]==row['m'])==bool(r['full_support'])
            assert (q,arm) not in checked
            checked.add((q,arm))
    assert len(checked)==len(records)*len(ARMS)
    rec_file=HERE/f'{panel}-events.json.gz'
    put(rec_file,[records[q] for q in sorted(records)])
    report=dict(plan=sha(HERE/'plan.json'),forecasts=sha(path/'forecast-seal.json'),outcomes=sha(path/'outcomes.json.gz'),
                records=sha(rec_file),partitions={})
    for scope in SCOPES:
        sub=[row for row in records.values() if scope=='minimum_two' or row['m']==2]
        report['partitions'][scope]=summarize(sub,plan['seed'],plan['boot'])
    put(HERE/f'{panel}-results.json',report)
    print(panel, len(records), report['partitions']['minimum_two']['contrasts'], flush=True)

if __name__=='__main__':
    command=argparse.ArgumentParser()
    command.add_argument('stage', choices=['lock','score'])
    command.add_argument('panel', nargs='?', choices=['availability','hash64','full'])
    args=command.parse_args()
    if args.stage=='lock':
        lock()
    else:
        assert args.panel
        analyze(args.panel)
