import gzip,hashlib,json,sys
from pathlib import Path
D=Path(__file__).resolve().parent
W=D.parents[1];R12=W/'graph_memory_round12'/'negative_external'
sys.dont_write_bytecode=True
sys.path.append(str(R12))
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(p):return sha(p.read_bytes())
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def dump(p,obj):
    b=json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(',',':'),indent=None if p.suffix=='.gz' else 1).encode()
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(gzip.compress(b,compresslevel=5,mtime=0) if p.suffix=='.gz' else b)
def obs(r):return r['iid']+':'+r['tool_call_id']