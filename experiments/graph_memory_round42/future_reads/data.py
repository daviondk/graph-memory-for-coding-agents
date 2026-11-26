from pathlib import Path
import gzip,hashlib,json
D=Path(__file__).resolve().parent;W=D.parents[1]
C=D.parent/"context_edits";L=D.parent/"lazy_validation"
S=W/"graph_memory_round41/structural_invalidation";G=W/"graph_memory_round40/guarded_updates"
V=W/"graph_memory_round38/edit_ready";H=W/"graph_memory_round37/code_visibility";E=H.parent/"edit_demand"
METHODS=("file","ast","content","range","edges","local","union")

def read(p):
    raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def bind(d,n):
    p=d/n;assert read(d/"manifest.json")["files"][n]==sha(p);return read(p)

def save(n,obj):
    p=D/n;b=(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,compresslevel=4,mtime=0) if p.suffix==".gz" else b)

