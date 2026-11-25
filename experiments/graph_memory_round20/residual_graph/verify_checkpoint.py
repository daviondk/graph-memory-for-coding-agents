"""Verify completed evidence inside either a worktree or the standalone reduced archive."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    m=json.loads((ROOT/'MANIFEST_SHA256.json').read_bytes())
    for name,digest in m.items():
        ref=(ROOT/name).resolve()
        assert ref.is_relative_to(ROOT.resolve()) and sha(ref)==digest
    for script in ['cpu_fallback/verify_bundle.py','evidence_flow/verify.py','evidence_flow/verify_diversity.py']:
        subprocess.run([sys.executable,'-B',str(ROOT/script)],check=True)
    print(len(m),'reduced-checkpoint files restored and verified')

if __name__=='__main__':
    main()
