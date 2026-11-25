import gzip, hashlib, json, sys
from pathlib import Path
R=Path(__file__).resolve().parent

def h(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def get(name): return json.loads((R/name).read_text(encoding='utf8'))

def verify():
    for file,lock,key in [('forecasts.jsonl.gz','forecast-lock.json','forecast'),('pointer-forecasts.jsonl.gz','pointer-forecast-lock.json','forecasts')]:
        assert h(R/file)==get(lock)[key]
        with gzip.open(R/file,'rt') as f: rows=[json.loads(x) for x in f]
        assert len(rows)==get(lock)['count']
        assert all(0<=r['used']<=r['budget'] for r in rows)
    for prefix in ('','schema-'):
        lock=get(prefix+'reader-forecast-lock.json')
        for k,f in [('inputs','reader-input-lock.json'),('forecasts','reader-forecasts.json')]:
            assert lock[k]==h(R/(prefix+f))
    z=get('results.json')['different|1536|fill']; assert z['n']==190 and z['metrics']['paired']['pair']==158
    z=get('pointer-results.json')['rag|512|one']; assert z['n']==49 and z['methods']['paired']['any_pair']==25
    rows=get('reader-results.json')['graded']; assert len(rows)==196 and sum(r['arm']=='paired' and r['outcome']=='TP' for r in rows)==21
    manifest={p.name:h(p) for p in sorted(R.iterdir()) if p.is_file() and p.name!='MANIFEST_SHA256.json'}
    if '--seal' in sys.argv:
        (R/'MANIFEST_SHA256.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    assert manifest==get('MANIFEST_SHA256.json')
    print('Verified',len(manifest),'files')
if __name__=='__main__': verify()

