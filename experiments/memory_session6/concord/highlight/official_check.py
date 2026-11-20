"""Direct crosscheck against the pinned upstream implementation."""
import gzip
import json
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/'upstream/src'),str(HERE.parent/'upstream/bench')]
from qa_agent.eval_pioneer import exact_match,token_f1
rows=json.loads(gzip.decompress((HERE/'projection.json.gz').read_bytes()))
for r in rows:
    assert exact_match(r['answer'],r['gold'])==r['em'] and abs(token_f1(r['answer'],r['gold'])-r['f1'])<1e-12
assert len(rows)==120
print('PASS pinned ConcordBench scorer on 80 new answers and 40 stock Concord answers.')
