from collections import Counter
from hashlib import sha256
from pathlib import Path
import gzip,json,os,sys
for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):
    os.environ[name]="1"
D=Path(__file__).resolve().parent
WORK=D.parents[1];UP=WORK/"memory_session5/serbench"
R34=WORK/"graph_memory_round34/external_transfer"
PUB=UP/"upstream/data/cal500"
sys.path.insert(0,str(UP/"upstream/src"))
import numpy as np
from serbench import _reference_scorer as native
def sha(p):
    return sha256(p.read_bytes()).hexdigest()
def get(p):
    raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)
def rows(p):
    with gzip.open(p,"rt",encoding="utf-8") as f:
        for line in f:yield json.loads(line)
def save(p,x):
    raw=json.dumps(x,sort_keys=True,separators=(",",":")).encode()
    p.write_bytes(gzip.compress(raw,compresslevel=6,mtime=0) if p.suffix==".gz" else raw)
def data():
    features=R34/"features.json.gz"
    assert sha(features)==get(R34/"input.json")["features"]
    return get(features)
