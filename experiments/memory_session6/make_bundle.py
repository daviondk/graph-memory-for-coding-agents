"""Create a portable snapshot of cycle six, pruning transient repositories and model caches."""
from pathlib import Path
import hashlib
import json
import os
import zipfile

ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT.parent.parent/'outputs'
SKIP_DIRS={'.git','__pycache__','.safety','pkgcache','venv','.venv','mirrors','hf-cache'}
PRUNE={'concord/work','concord/highlight/work','concord/controls/work','report/temp','concord/upstream/examples','concord/upstream/tests','concord/upstream/asset','concord/upstream/bench/tests'}
OMIT={'repair/runtime/server.stderr','repair/runtime/server.stdout'}
KEEP_REPORT={'qa.json','released.json','agent-memory-session6-results.docx','agent-memory-session6-results.pdf'}

def include(path):
    key=path.relative_to(ROOT).as_posix()
    if key in OMIT or path.suffix in {'.pyc','.pyo','.tmp','.pid','.obj','.o','.exe','.dll'} or path.name in {'.env','.DS_Store','trec_eval'}:
        return False
    if key.startswith('report/final/') and path.name not in KEEP_REPORT:
        return False
    return True

def files():
    for here,dirs,items in os.walk(ROOT):
        current=Path(here)
        dirs[:]=sorted(d for d in dirs if d not in SKIP_DIRS and (current/d).relative_to(ROOT).as_posix() not in PRUNE and not d.startswith('validity-replay-'))
        for name in sorted(items):
            p=current/name
            if include(p):
                yield p

def main():
    OUTPUT.mkdir(exist_ok=True)
    target=OUTPUT/'agent-memory-session6-records.zip'
    tmp=target.with_suffix('.tmp')
    hashes={}
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as archive:
        for path in files():
            name=path.relative_to(ROOT).as_posix()
            data=path.read_bytes()
            hashes[name]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            compression=zipfile.ZIP_STORED if path.suffix in {'.gz','.zip','.png','.pdf','.docx'} else zipfile.ZIP_DEFLATED
            archive.writestr(name,data,compress_type=compression)
        archive.writestr('MANIFEST.json',json.dumps({'series':6,'entries':hashes},indent=1))
    os.replace(tmp,target)
    print(len(hashes),'entries;',target.stat().st_size,'bytes;',hashlib.sha256(target.read_bytes()).hexdigest())

if __name__=='__main__':
    main()
