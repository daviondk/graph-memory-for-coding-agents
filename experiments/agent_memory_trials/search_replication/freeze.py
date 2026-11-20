import datetime as dt
import json
from pathlib import Path
from build_study import ROOT, digest, dump

path = ROOT / "freeze.json"
if path.exists() or (ROOT / "runs").exists():
    raise SystemExit("Freeze already exists or data collection has started.")
files = sorted([p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts])
dump(path, dict(frozen_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p)) for p in files]))
print("freeze SHA256", digest(path), len(files), "files")
