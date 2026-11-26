"""Create the release manifest exactly once, without exposing solver workspaces."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
files = set(ROOT.glob("*.py")) | set(ROOT.glob("*.md")) | set(ROOT.glob("*.lock")) | {ROOT/"screen.json"}
files.update(p for p in (ROOT/"specs").rglob("*") if p.is_file())
for phase in ("stock", "extra", "native"):
    for patch in ("base", "reference"):
        for suffix in ("json", "log", "xml"):
            files.add(ROOT/"smoke"/f"{phase}-{patch}.{suffix}")
manifest = {"protocol": "R38 target selection and PyBaMM grader controls", "files": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}}
with (ROOT/"manifest.json").open("x", encoding="utf8", newline="\n") as output:
    output.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
