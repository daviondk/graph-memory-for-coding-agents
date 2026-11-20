"""Common serialization and SHA identities for the portable study."""
import gzip
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
WRITE=HERE.parent/'write'
def digest(b):return hashlib.sha256(b).hexdigest()
def ident(s):return digest(s.encode())[:24]
def pack(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def save(p,x):
    b=pack(x)
    if p.suffix=='.gz':b=gzip.compress(b,mtime=0)
    if p.exists():assert load(p)==x,p.name
    else:
        tmp=p.with_suffix('.tmp');tmp.write_bytes(b);tmp.replace(p)
