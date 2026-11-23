"""Copy compact stage logs and seal the published study files."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUN=Path('D:/CodexResearch/x20-isetrace-bounded-dense')
logs=ROOT/'logs';logs.mkdir(exist_ok=True)
for step in ('inputs','encode','finish','physical','sources'):
    for suffix in ('.log','.err'):
        p=RUN/(step+suffix);shutil.copyfile(p,logs/p.name)
def digest(p):
    with p.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
assert (ROOT/'results.json').exists() and (ROOT/'source-verification.json').exists()
files={p.relative_to(ROOT).as_posix():digest(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='MANIFEST_SHA256.json' and '__pycache__' not in p.parts}
out=ROOT/'MANIFEST_SHA256.json';out.write_bytes((json.dumps(files,sort_keys=True,indent=2)+'\n').encode())
print(len(files),digest(out))

