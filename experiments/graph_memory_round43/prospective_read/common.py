from pathlib import Path
import gzip,hashlib,json
import numpy as np

D=Path(__file__).resolve().parent;W=D.parents[1]
F=W/"graph_memory_round42/future_reads";C=F.parent/"context_edits";G=W/"graph_memory_round40/guarded_updates"
H=W/"graph_memory_round37/code_visibility";V=W/"graph_memory_round38/edit_ready"
METHODS=("original","target","novel","near","model")

def read(p):
    raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def h(t):return hashlib.sha256(t.encode()).hexdigest()
def bind(d,n):
    p=d/n;assert sha(p)==read(d/"manifest.json")["files"][n];return read(p)
def save(n,v):
    p=D/n;b=(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,compresslevel=4,mtime=0) if p.suffix==".gz" else b)


def prefix(blocks):
    used=0;head=[]
    for b in blocks:
        if used+b["cost"]>1024:break
        used+=b["cost"];head.append(b["idx"])
    return head,2048-used


def choose(blocks,major):
    head,capacity=prefix(blocks)
    # Integer lexicographic objectives: secondary priorities cannot overcome one unit of primary value.
    factor=1+sum(abs(b["prior"]) for b in blocks)
    keys=[];record=[];best=np.zeros(capacity+1,dtype=np.int64)
    for b in blocks[len(head):]:
        idx,cost=b["idx"],b["cost"]
        if cost>capacity:continue
        objective=int(major.get(idx,0))*factor+b["prior"]
        proposal=best[:capacity+1-cost]+objective
        flags=proposal>best[cost:]
        np.maximum(best[cost:],proposal,out=best[cost:])
        record.append((cost,flags));keys.append(idx)
    picked=[]
    for idx,(cost,flags) in reversed(list(zip(keys,record))):
        if capacity>=cost and flags[capacity-cost]:
            picked.append(idx);capacity-=cost
    return head+list(reversed(picked))


def weights(bs,method):
    if method=="original":return {}
    if method=="target":return {b["idx"]:len(b["lines"])*1000000 for b in bs}
    if method=="novel":return {b["idx"]:len(b["novel"])*1000000 for b in bs}
    if method=="near":return {b["idx"]:int(round(1000000*sum(1/(1+d/32) for d in b["distance"]))) for b in bs}
    raise KeyError(method)

