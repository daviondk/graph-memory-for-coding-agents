"""Single entry point for the release audit. Needs R50, transfer and routing, CPU only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

BASE=Path(__file__).resolve().parent
def main():
    files=json.loads((BASE/"manifest.json").read_bytes())["files"]
    for name,h in files.items():
        assert hashlib.sha256((BASE/name).read_bytes()).hexdigest()==h,name
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",PYTHONDONTWRITEBYTECODE="1")
    for name in ("verify.py","verify_complete.py","confirm/verify.py"):
        subprocess.run([sys.executable,"-B","-X","utf8",str(BASE/name)],check=True,cwd=BASE,env=env)
    print(f"Verified {len(files)} baseline files, including all prospective confirmation artifacts.")

if __name__=="__main__":
    main()
