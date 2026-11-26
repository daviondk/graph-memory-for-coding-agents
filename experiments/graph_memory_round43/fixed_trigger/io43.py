from pathlib import Path
import gzip,hashlib,json,os
D=Path(__file__).resolve().parent
W=D.parents[1]
R42=W/"graph_memory_round42/causal_ablation"
R41=W/"graph_memory_round41/prefix_native"
OFF=W/"graph_memory_round22/native_multiseed/official580"
SEEDS=(13,17,29,37,41)
ARMS=("full","rich","cross","local","sham","dense","R35","native_wo")
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,obj):
    raw=(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    tmp=p.with_suffix(p.suffix+".new")
    tmp.write_bytes(gzip.compress(raw,compresslevel=4,mtime=0) if p.suffix==".gz" else raw)
    os.replace(tmp,p)
def signed(p):
    assert sha(p)==read(p.parent/"manifest.json")["files"][p.name]
    return read(p)
