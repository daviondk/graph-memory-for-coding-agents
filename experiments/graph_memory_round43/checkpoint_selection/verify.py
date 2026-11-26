"""Verify all signed local audit inputs and repeat the CPU reconstruction."""
from hashlib import sha256
import json
from pathlib import Path
from analyze import run
D=Path(__file__).resolve().parent
m=json.loads((D/'manifest.json').read_bytes())['files']
assert all(sha256((D/n).read_bytes()).hexdigest()==h for n,h in m.items())
result=run()
assert json.loads((D/'results.json').read_bytes())==result
print('Verified two original protocols, 160 dev epochs, 10 numerical checkpoint comparisons and 5 matched test arrays.')

