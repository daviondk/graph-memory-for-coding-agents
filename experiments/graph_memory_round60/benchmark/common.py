import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def load(path):
    b = path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix == ".gz" else b)

def save(name, obj):
    path = HERE / name
    b = (json.dumps(obj, ensure_ascii=True, sort_keys=True, indent=None if path.suffix == ".gz" else 2) + "\n").encode()
    path.write_bytes(gzip.compress(b, mtime=0) if path.suffix == ".gz" else b)

