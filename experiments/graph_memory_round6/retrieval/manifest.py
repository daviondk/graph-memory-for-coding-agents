"""Consolidate hashes of the deliverable, copied data and additional source receipts."""
import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
out={}
for p in sorted(D.rglob('*')):
    r=p.relative_to(D)
    if not p.is_file() or 'corpus' in r.parts or 'store' in r.parts or 'home' in r.parts or '__pycache__' in r.parts:continue
    if p.name=='MANIFEST.json' or p.suffix=='.log' and p.name!='index.log':continue
    out[r.as_posix()]={'bytes':p.stat().st_size,'sha256':sha(p)}
(D/'MANIFEST.json').write_text(json.dumps(out,indent=2),encoding='utf8')
print(len(out),'files recorded')

