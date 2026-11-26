import gzip
import json
from pathlib import Path
import math
import hashlib

d = Path(__file__).resolve().parent
rec = json.loads((d/'results.json').read_text('utf8'))
flags = json.loads(gzip.decompress((d/'strata.json.gz').read_bytes()))
pairs = json.loads(gzip.decompress((d/'paired.json.gz').read_bytes()))
assert len(set(r[0] for r in pairs)) == len(pairs) == 901
assert sum(flags.values()) == 8 and len(flags) == 2000
for idx,name in enumerate(('no_identifier','identifier')):
    subset = [r for r in pairs if r[2] == idx]
    assert all(bool(idx) == flags[r[0]] for r in subset)
    g = rec['groups'][name]
    assert (len(subset),len({r[1] for r in subset})) == (g['n'],g['trajectories'])
    for arm,col in (('value',3),('rich',4)):
        assert math.isclose(sum(sum(r[col]) for r in subset)/(len(subset)*5),g[arm])
    assert math.isclose(g['value']-g['rich'],g['delta'],abs_tol=1e-12)
assert rec['groups']['no_identifier']['ci'][0]>0 and rec['groups']['identifier']['nonempty_bootstraps']<10000
assert rec['label_lock_sha256'] == hashlib.sha256((d/'label-lock.json').read_bytes()).hexdigest()
print('Verified 901 paired outcomes, 2000 frozen strata, five seeds and both raw group means.')
