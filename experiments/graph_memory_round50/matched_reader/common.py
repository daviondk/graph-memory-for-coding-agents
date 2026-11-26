import gzip
import hashlib
import json
from pathlib import Path
D=Path(__file__).resolve().parent
W=D.parents[1]
SEEDS=(13,17,29,37,41)
MODES=("original_dp","guarded_dp","fast_full","firstfit","value")
CONFIG=("recall","full_support")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def put(p,data):
    b=(json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if p.suffix==".gz" else b)

