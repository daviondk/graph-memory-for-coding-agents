from pathlib import Path
import gzip,hashlib,json
D=Path(__file__).resolve().parent;W=D.parents[1];R=W/"graph_memory_round23";F=W/"graph_memory_round24/frontier_open"
PVT=Path("D:/CodexResearch/x20-r25-squad");SQUAD=PVT/"dev-v1.1.json"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,x):
    raw=(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)
    return sha(p)
def check():
    for k,h in read(D/"plan.json")["local_inputs"].items():assert sha(W/k)==h
    assert sha(SQUAD)=="95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9"
PAIRS=(("adaptive","right"),("adaptive","both"))
ARMS=("right","left","feasible_left","both","adaptive")
