"""Offline replay of the decision writer and independent snapshot-based scoring."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import run

ROOT = Path(__file__).resolve().parent

def digest_stream(stream):
    return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    for lock in ['projection_lock.json', 'decision_lock.json']:
        for name, expected in json.loads((ROOT / lock).read_bytes()).items():
            with (ROOT / name).open('rb') as stream:
                assert digest_stream(stream) == expected, name
    with tempfile.TemporaryDirectory(prefix='validity-replay-', dir=ROOT) as path:
        dest = Path(path)
        for name in ('projection', 'natural'):
            shutil.copytree(ROOT / name, dest / name)
        for name in ('policy.py', 'run.py', 'PROTOCOL.md', 'MECHANISMS.md'):
            shutil.copy(ROOT / name, dest / name)
        run.ROOT = dest
        try:
            run.main()
        finally:
            run.ROOT = ROOT
        for name in ('decisions.jsonl.gz', 'wire_costs.json.gz'):
            with gzip.open(ROOT / name) as left, gzip.open(dest / name) as right:
                assert digest_stream(left) == digest_stream(right), name
    for name in ('score.py', 'exposure.py', 'stream/sim.py'):
        subprocess.run([sys.executable, '-B', str(ROOT / name), '--verify'], cwd=ROOT, check=True)
    print('PASS: all decisions regenerated without gold, gold scoring and every stream packet replayed.')

if __name__ == '__main__':
    main()
