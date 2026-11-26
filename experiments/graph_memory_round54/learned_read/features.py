"""Freeze the allowed candidates and a compact design matrix without opening relevance labels."""
import gzip,hashlib,json,math
from pathlib import Path
D=Path(__file__).resolve().parent
SRC=D.parent/"next_read"
METHODS=("embed4","embed8","jina","lexical","nomic","pplx","repomap")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    s=p.read_bytes();return json.loads(gzip.decompress(s) if p.suffix==".gz" else s)
def put(f,v):
    p=D/f;s=(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(s,mtime=0) if f.endswith(".gz") else s)
def ranks(seq):
    out={}
    for i,p in enumerate(seq,1):out.setdefault(p,i)
    return out
def main():
    seal=read(SRC/"fusion-seal.json");e=read(SRC/"explicit-seal.json")
    for name in ("fusion-inputs.json.gz","fusion-choices.json.gz"):assert sha(SRC/name)==seal[name]
    assert e["decisions"]==sha(SRC/"explicit-decisions.json.gz")
    draft=read(SRC/"fusion-inputs.json.gz");ctx=read(SRC/"explicit-decisions.json.gz")
    old=read(SRC/"fusion-choices.json.gz");proj={}
    for q,d in draft.items():
        order=d["lexical_order"];assert order and len(order)==len(set(order)) and set(METHODS)==set(d["ranks"])
        assert not set(order)&set(ctx[q]["opened"]) and set(ctx[q]["strict"])<=set(ctx[q]["opened"])
        allowed=set(order);mem=list(dict.fromkeys(p for p in d["proposals"] if p in allowed))
        assert mem==ctx[q]["new_suggestions"]
        cols=[ranks(d["ranks"][m]) for m in METHODS]+[ranks(mem)]
        X=[[r[p] if p in r else 0 for r in cols] for p in order]
        rrf=max(range(len(order)),key=lambda i:sum(1/(60+r) for r in X[i][:7] if r))
        assert order[rrf]==old[q]["chosen"]["static_seven"]
        proj[q]=dict(group=ctx[q]["repo"],paths=order,ranks=X,strict=ctx[q]["strict"],rrf7=order[rrf],rrf3=old[q]["chosen"]["triple"])
    assert len(proj)==283
    put("projection.json.gz",proj)
    put("registration.json",dict(n=len(proj),source_fusion=sha(SRC/"fusion-seal.json"),source_explicit=sha(SRC/"explicit-seal.json"),
        projection=sha(D/"projection.json.gz"),protocol=sha(D/"PROTOCOL_RU.md"),builder=sha(Path(__file__)),model=sha(D/"evaluate.py"),
        members=list(METHODS),training_weight_per_query=1))
if __name__=="__main__":main()
