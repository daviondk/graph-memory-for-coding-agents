import gzip,json,hashlib
from pathlib import Path
from collections import Counter
d=Path(__file__).resolve().parent
buf=(d/'traces.json.gz').read_bytes();s=json.loads((d/'seal.json').read_bytes())
assert hashlib.sha256(buf).hexdigest()==s['sha_rows']
rows=json.loads(gzip.decompress(buf));out=json.loads((d/'results.json').read_bytes())
assert len(rows)==s['n']==1207
for kind in ('net_count','edge_changed','flag_changed'):
    summed=Counter()
    for r in rows:
        v=r['metrics'][kind];summed.update(v)
        assert v.get('visits',0)==v['unique']+v.get('hits',0)
        assert v['unique']==v['singletons']+v['repeat_keys']
    assert all(summed[k]==v for k,v in out[kind]['totals'].items())
    assert summed['groups']==31279
assert out['net_count']['totals']['joint']==2415
print('Verified three paired definitions and all trajectory totals.')
