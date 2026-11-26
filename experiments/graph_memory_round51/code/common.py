"""Round 51: deterministic file IO and shared, label-free identities."""
from pathlib import Path
import gzip
import hashlib
import json
import os

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parents[1]
UPSTREAM = Path(os.environ.get("SERBENCH_ROOT", "D:/CodexResearch/x20-bench-workspace/work/memory_session5/serbench/upstream"))
PLAN = "a9c8568b546620e1e93a11f3b2d62ecb50b02b11d33b6f37d8213da8a9c1a4d3"
WEIGHTS = (0, .25, -.25, .5, -.5, 1, -1)

def read(path):
    data = Path(path).read_bytes()
    return json.loads(gzip.decompress(data) if str(path).endswith(".gz") else data)

def save(name, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf8")
    (HERE / name).write_bytes(gzip.compress(data, mtime=0) if name.endswith(".gz") else data)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def key(fields):
    payload = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(payload).hexdigest()

def score(indices, judgment):
    selected = set(indices)
    groups = judgment["groups"]
    hits = [len(selected.intersection(members)) >= minimum for minimum, _, members in groups]
    complete = all(hits) or any(set(alt).issubset(selected) for alt in judgment["alts"])
    return int(complete), sum(hits) / len(hits) if hits else 1.

