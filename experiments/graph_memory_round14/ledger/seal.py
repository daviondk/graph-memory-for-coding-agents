import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
files=[p for p in sorted(D.rglob("*")) if p.is_file() and not (set(p.relative_to(D).parts)&{"vendor","scratch","__pycache__"}) and p.name!="MANIFEST_SHA256.json"]
man={p.relative_to(D).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
m=D/"MANIFEST_SHA256.json";m.write_text(json.dumps(man,indent=1)+"\n",encoding="utf8")
print(len(man),sum(f.stat().st_size for f in files),hashlib.sha256(m.read_bytes()).hexdigest())
