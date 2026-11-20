"""Check relative report links and write archive hashes in a separate verification manifest."""
import hashlib
import json
import re
from pathlib import Path

D = Path(__file__).resolve().parent
files = sorted(p for p in D.rglob("*") if p.is_file() and "__pycache__" not in p.parts
               and p.name != "MANIFEST_SHA256.json")
for p in files:
    if p.suffix == ".md":
        for url in re.findall(r"\[[^\n\]]+\]\(([^)]+)\)", p.read_text(encoding="utf8")):
            if "://" not in url:
                assert (p.parent / url).exists(), (p.name, url)
hashes = {p.relative_to(D).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
m = D / "MANIFEST_SHA256.json"
m.write_text(json.dumps(hashes, ensure_ascii=False, indent=1) + "\n", encoding="utf8")
print(len(files), "files,", sum(p.stat().st_size for p in files), "bytes excluding manifest,", hashlib.sha256(m.read_bytes()).hexdigest())
