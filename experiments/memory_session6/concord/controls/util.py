import pathlib,gzip,json,hashlib,datetime,os
ROOT=pathlib.Path(__file__).resolve().parent
BASE=ROOT.parent
def digest(b):return hashlib.sha256(b).hexdigest()
def encode(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
def read(p):
    p=pathlib.Path(p);return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def save(p,o):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():assert read(p)==o,p;return
    v=encode(o);t=p.with_suffix('.tmp');t.write_bytes(gzip.compress(v,mtime=0) if p.suffix=='.gz' else v);os.replace(t,p)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def check(p,expected):assert digest(p.read_bytes())==expected,p

