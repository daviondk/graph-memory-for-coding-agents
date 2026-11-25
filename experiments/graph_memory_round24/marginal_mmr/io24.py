from pathlib import Path
import gzip,hashlib,json
D=Path(__file__).resolve().parent;W=D.parents[1];R=W/"graph_memory_round23"
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,row):
    data=(json.dumps(row,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(data,mtime=0) if p.suffix==".gz" else data)
    return sha(p)
def check():
    for n,h in read(D/"plan.json")["inputs"].items():assert sha(W/n)==h
PAIRS=(("max_50","first_positive"),("union_50","max_50"))
