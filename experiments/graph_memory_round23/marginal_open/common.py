from pathlib import Path
import gzip,hashlib,json
D=Path(__file__).resolve().parent
W=D.parents[1]
PARENT=D.parent/"read_causes"
PRIVATE=Path("D:/CodexResearch/x20-isetrace-fine-train/marginal-open")
TOK=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    data=json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()+b"\n"
    p.write_bytes(gzip.compress(data,mtime=0) if p.suffix==".gz" else data)
def check_plan():
    z=read(D/"plan.json")
    assert z["before_forecast"]
    for n,h in z["inputs"].items():assert sha(D/n)==h

