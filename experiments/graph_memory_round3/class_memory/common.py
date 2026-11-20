import gzip, hashlib, json
from pathlib import Path
D=Path(__file__).resolve().parent
ROOT=D.parents[2]
def sha(v):
    return hashlib.sha256(v if isinstance(v,bytes) else v.encode()).hexdigest()
def read(p):
    data=Path(p).read_bytes()
    return json.loads(gzip.decompress(data) if str(p).endswith(".gz") else data)
def save(p,data):
    p=Path(p);raw=json.dumps(data,ensure_ascii=True,separators=(",",":")).encode()
    if p.suffix==".gz":raw=gzip.compress(raw,mtime=0)
    p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_suffix(p.suffix+".tmp");temp.write_bytes(raw);temp.replace(p)
