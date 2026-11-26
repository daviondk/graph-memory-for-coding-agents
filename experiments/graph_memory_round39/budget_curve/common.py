from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

D = Path(__file__).resolve().parent
W = D.parents[1]
GLOBAL = D.parent / "global_packet"
REMAIN = D.parent / "remaining_budget"
SEEDS = (13,17,29,37,41)
BUDGETS = (256,512,1024,2048,4096,8192)
ORDERS = ("R35","full_rgcn","wo_chunk_adjacency")
SELECTORS = ("strict","firstfit","graph_dp")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    b = p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)


def save(p, data):
    b = (json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    if p.suffix == ".gz":
        b = gzip.compress(b,compresslevel=4,mtime=0)
    if p.exists():
        assert p.read_bytes()==b, p
    else:
        tmp = p.with_suffix(p.suffix+".tmp")
        tmp.write_bytes(b)
        tmp.replace(p)


def log(event, **details):
    with (D/"run-log.jsonl").open("a",encoding="utf-8") as f:
        f.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),event=event,**details),sort_keys=True)+"\n")
