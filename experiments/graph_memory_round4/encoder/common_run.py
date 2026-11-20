import gzip
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

D = Path(__file__).resolve().parent
R = D.parent / "repo"

def hashfile(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()

def save(name, value):
    (D / name).write_text(json.dumps(value, indent=1, ensure_ascii=False), encoding="utf8")

def load(path):
    return json.loads(Path(path).read_bytes())

def now():
    return datetime.now(timezone.utc).isoformat()

def cases():
    wanted = load(R / "paired_roster.json")
    roster = load(R / "strict_roster.json")
    for path in sorted((R / "inputs").glob("java_*_test_*.parquet")):
        panel = path.stem.rsplit("_", 1)[0]
        mapping = {row: idx for row, idx in roster[path.stem] if idx in wanted[panel]}
        yield path, panel, mapping

def readgz(path):
    with gzip.open(path, "rt", encoding="utf8") as file:
        yield from map(json.loads, file)

def writegz(path, rows):
    with gzip.open(path, "wt", encoding="utf8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n")
