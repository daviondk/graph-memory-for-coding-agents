import gzip,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent;W=D.parents[1];R=W/"graph_memory_round25/directional_open"
P=Path("D:/CodexResearch/x20-r26-directional-io");DB=P/"physical.sqlite"
def sha_file(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def load(f):return json.loads(gzip.decompress(f.read_bytes()) if f.suffix==".gz" else f.read_bytes())
def save(f,info):
    b=(json.dumps(info,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode()
    f.write_bytes(gzip.compress(b,mtime=0) if f.suffix==".gz" else b)
    return sha_file(f)
def freeze():
    z={"before_measurements":True,"plan":sha_file(D/"PROTOCOL_RU.md"),"source":sha_file(R/"manifest.json"),"n_each":96,"warm":21,"fresh":3,"seed":26017,"stride":256}
    f=D/"plan.json"
    if f.exists():assert load(f)==z
    else:save(f,z)
if __name__=="__main__":freeze();print(sha_file(D/"plan.json"))
