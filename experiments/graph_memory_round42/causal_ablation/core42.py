from pathlib import Path
import gzip,hashlib,json,os
D=Path(__file__).resolve().parent
W=D.parents[1]
R41=W/"graph_memory_round41/prefix_native"
CAUSAL=R41.parent/"causal_budget"
OFF=W/"graph_memory_round22/native_multiseed/official580"
SEEDS=(13,17,29,37,41)


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)


def save(p,x):
    data=(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    tmp=p.with_suffix(p.suffix+".new")
    tmp.write_bytes(gzip.compress(data,mtime=0,compresslevel=4) if p.suffix==".gz" else data)
    os.replace(tmp,p)


def signed(directory,name):
    p=directory/name
    assert sha(p)==read(directory/"manifest.json")["files"][name]
    return read(p)


def firstfit(order,c):
    cap=2048;out=[]
    for v in order:
        if c[v]<=cap:
            cap-=int(c[v]);out.append(int(v))
    return out
