import gzip
import hashlib
import json
from pathlib import Path
from experiment import model_check
root=Path(__file__).resolve().parent
checks=json.loads((root/'checks.json').read_text('utf8'))
stats=json.loads((root/'results.json').read_text('utf8'))
assert checks['bounded_checks']==model_check()
raw=(root/'trace-results.json.gz').read_bytes()
assert hashlib.sha256(raw).hexdigest()==checks['records_sha256']
rows=json.loads(gzip.decompress(raw))
assert len(rows)==stats['trajectories']==1207
assert sum(r['groups'] for r in rows)==stats['groups']==31279
for arm,g in stats['per_arm'].items():
    assert sum(r['arms'][arm][0] for r in rows)==g['reads']
    assert sum(r['arms'][arm][1] for r in rows)==g['groups_with_read']
assert checks['max_witnesses']==64
assert stats['per_arm']['3-1']['reads']==343 and stats['per_arm']['3-0']['reads']==490
print('Verified six state machines and branch totals on 1207 trajectories.')
