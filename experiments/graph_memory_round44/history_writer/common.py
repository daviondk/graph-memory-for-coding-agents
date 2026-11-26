from collections import Counter,defaultdict
from pathlib import Path
import gzip,hashlib,json,struct,sys
D=Path(__file__).resolve().parent;W=D.parents[1];V=W/"graph_memory_round40/view_fidelity"
G=V.parent/"guarded_updates";H=W/"graph_memory_round37/code_visibility";E=H.parent/"edit_demand"
C=W/"graph_memory_round42/context_edits";F=C.parent/"future_reads";RAW=Path("D:/CodexResearch/x20-r31-handoff")
MODES=("latest","lru","first","lfu","distinct");CAPS=(2048,8192,32768)
HEADER=struct.Struct(">II");REF=struct.Struct(">32sIIIHI");LENGTH=struct.Struct(">H")
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def signed(d,n):
    p=d/n;assert sha(p)==read(d/"manifest.json")["files"][n];return read(p)
def save(n,v):
    p=D/n;b=(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,compresslevel=4,mtime=0) if p.suffix==".gz" else b)
def label(mode,cap):return mode+("_unlimited" if cap is None else "_"+str(cap))

