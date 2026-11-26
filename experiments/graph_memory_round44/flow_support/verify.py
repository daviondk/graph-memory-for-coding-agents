from pathlib import Path
import hashlib,gzip,json
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256((D/p).read_bytes()).hexdigest()
r=json.loads((D/'results.json').read_bytes());rows=json.loads(gzip.decompress((D/'question-strata.json.gz').read_bytes()))
assert len(rows)==2000 and sha('question-strata.json.gz')==r['source']
base=[v for v in rows if not v['pilot'] and v['full']==v['available']]
for group,pred in [('all',lambda v:True),('hit',lambda v:v['incidence']>0),('none',lambda v:v['incidence']==0),
                        ('matched_hit',lambda v:v['cost']>2048 and v['endpoint_candidates'] and v['incidence']>0),
                        ('matched_none',lambda v:v['cost']>2048 and v['endpoint_candidates'] and v['incidence']==0)]:
    g=[v for v in base if pred(v)];known=r['groups'][group];assert len(g)==known['n']
    for k,x in known['means'].items():assert abs(sum(sum(v['fs'][k]) for v in g)/(5*len(g))-x)<1e-11
for v in r['interactions']:
    a,b=[r['groups'][v[k]]['means'] for k in ('left','right')]
    assert abs(a['value']-a['rich']-b['value']+b['rich']-v['delta'])<1e-12
if (D/'manifest.json').exists():assert all(sha(k)==v for k,v in json.loads((D/'manifest.json').read_bytes())['files'].items())
print('Verified all primary strata and all five interactions')
