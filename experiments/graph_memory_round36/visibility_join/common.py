from pathlib import Path
import hashlib,json,gzip
D=Path(__file__).resolve().parent; W=D.parents[1]; M=D.parent/"materialized_append"; V=D.parent/"visibility_oracle"
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def hashobj(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,x):
    b=(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode();p.write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if p.suffix==".gz" else b)
def key(t):return hashlib.sha256(("r36-visibility-sql/v1/"+t).encode()).hexdigest()
def degrees(pairs):
    d={}
    for a,b in pairs:
        d.setdefault(a,[0,0])[0]+=1;d.setdefault(b,[0,0])[1]+=1
    return sorted((k,*v) for k,v in d.items())
