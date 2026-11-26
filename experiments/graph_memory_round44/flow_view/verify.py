from pathlib import Path
import gzip,hashlib,json,math
D=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r=read(D/'results.json');rows={}
for i in range(8):
    s=D/f'shard-{i}.json';p=D/f'trace-{i}.json.gz';records=read(p)
    assert sha(s)==r['shards'][str(i)] and sha(p)==read(s)['sha'] and not rows.keys()&records.keys()
    rows.update(records)
assert len(rows)==1207
assert all(sum(z['counts'].get(key,0) for z in rows.values())==v for key,v in r['totals'].items())
for j,key in enumerate(r['baselines']):
    cost=[sum(v[key][i] for z in rows.values() for v in z['timing']) for i in (0,1)]
    assert cost==r['time_ns_sums'][j]
if (D/'manifest.json').exists():
    assert all(sha(D/k)==h for k,h in read(D/'manifest.json')['files'].items())
print('Verified observations and paired timings on 1207 trajectories')
