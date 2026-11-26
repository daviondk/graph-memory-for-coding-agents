"""Replay every registered point through the persisted SQL index."""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
root=Path(__file__).resolve().parent
meta=json.loads((root/'run.json').read_bytes())
stats=json.loads((root/'results.json').read_bytes())
rows=json.loads(gzip.decompress((root/'pairs.json.gz').read_bytes()))
db=sqlite3.connect((root/'planes.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
assert db.execute('pragma integrity_check').fetchone()==('ok',) and db.execute('pragma foreign_key_check').fetchone() is None
assert len(rows)==stats['distinct_pairs']==1862
assert meta['small']==8820
total=0
for row in rows:
    pair=row['pair']
    assert db.execute('select q,s,t from pair where id=?',(pair,)).fetchone()==(row['q'],row['s'],row['t'])
    for x,y,winner,cert in row['tests']:
        got=db.execute('select packet from plane where pair_id=? order by v+a*?+b*? desc,priority limit 1',(pair,x,y)).fetchone()[0]
        assert got==winner and (not cert or got==row['zero'])
        total+=1
assert total==stats['distinct_checks']==106134
print('Verified 106134 winner identities from the persisted two-source index.')
