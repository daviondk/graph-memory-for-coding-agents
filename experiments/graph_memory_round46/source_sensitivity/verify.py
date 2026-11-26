from pathlib import Path
from hashlib import sha256
import sqlite3,json,gzip
root=Path(__file__).resolve().parent
meta=json.loads((root/'run.json').read_bytes())
stats=json.loads((root/'results.json').read_bytes())
raw=(root/'sources.json.gz').read_bytes()
assert sha256(raw).hexdigest()==meta['ledger_sha256']
rows=json.loads(gzip.decompress(raw))
db=sqlite3.connect((root/'intervals.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
counts=[0,0,0,0]
for r in rows:
    bounds=db.execute('select lo,hi from valid where q=? and source=?',(r['q'],r['source'])).fetchone()
    assert bounds==(r['lo'],r['hi'])
    for d,same,sign,hamming,_ in r['samples']:
        assert (bounds[0]<=d<=bounds[1])==bool(same)==(hamming==0)
        assert not sign or same
        counts[3]+=1
        if d in meta['grid']:
            counts[0]+=1
            counts[1]+=same
            counts[2]+=sign
assert counts==[15168,9129,7911,24896] and len(rows)==2528
assert (stats['groups']['all']['same'],stats['groups']['multi']['same'])==(9129,1995)
print('Verified all stored intervals, 15168 experimental changes, 24896 direct comparisons.')
