import gzip,hashlib,json,os,unicodedata
from pathlib import Path
from urllib.parse import unquote
D=Path(__file__).resolve().parent
W=D.parents[1]
PRIVATE=Path(os.getenv("HREF_WORK","D:/CodexResearch/x20-r50-hyperlink"))
CONFIG={"dev":"qa_external","train":"qa_replication"}
URL="https://dl.dropboxusercontent.com/s/wlhw26kik59wbh8/para_with_hyperlink.zip"
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def write(p,v):
    b=(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0,compresslevel=3) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def textsha(s):return hashlib.sha256(s.encode()).hexdigest()
def title(s):return unicodedata.normalize("NFC"," ".join(s.replace("_"," ").split()))
def compact(s):return "".join(s.split())
def visible(split):return W.parents[1]/("x20-r50-"+CONFIG[split].replace("_","-"))/"visible.json.gz"
def candidates():
    wanted=set();sources=set()
    for split,study in CONFIG.items():
        records=read(visible(split));orders=read(D.parent/study/"orders.json.gz")
        assert set(records)==set(orders)
        for q,(_,docs) in records.items():
            wanted.update(title(t) for _,t,_ in docs);sources.add(title(docs[orders[q]["seed"]][1]))
    return wanted,sources

