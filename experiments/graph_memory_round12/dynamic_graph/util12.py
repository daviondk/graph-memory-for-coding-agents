import base64,gzip,hashlib,json,struct,sys
from pathlib import Path
D=Path(__file__).resolve().parent
R10=D.parents[1]/'graph_memory_round10'/'multiset'
sys.path.insert(0,str(R10))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):
    raw=json.dumps(x,ensure_ascii=False,sort_keys=True,indent=None if p.suffix=='.gz' else 1,separators=(',',':')).encode()
    p.parent.mkdir(exist_ok=True,parents=True)
    p.write_bytes(gzip.compress(raw,compresslevel=4,mtime=0) if p.suffix=='.gz' else raw)
def load(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)
def u32(i):return struct.pack('<I',i)
def event_raw(words):return json.dumps(sorted(words),separators=(',',':'),ensure_ascii=False).encode()
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
