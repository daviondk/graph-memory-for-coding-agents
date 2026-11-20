"""Crosscheck the offline scorer with the pinned official Python module on every raw answer."""
import gzip
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'upstream/src'),str(ROOT/'upstream/bench')]
from qa_agent.eval_pioneer import exact_match,token_f1
num=0
for name in ['published_projection.json.gz','local_projection.json.gz']:
    fn=ROOT/name
    if not fn.exists():
        continue
    for row in json.loads(gzip.decompress(fn.read_bytes())):
        assert exact_match(row['answer'],row['gold'])==row['em']
        assert abs(token_f1(row['answer'],row['gold'])-row['f1'])<1e-12
        num+=1
print('PASS pinned qa_agent.eval_pioneer on',num,'archived answers.')
