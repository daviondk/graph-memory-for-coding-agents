"""Package experiment evidence and sources; Git mirrors/model weights stay in the pinned local stores."""
from pathlib import Path
from hashlib import sha256
from zipfile import ZipFile, ZIP_DEFLATED
import json

ROOT=Path(__file__).resolve().parent
DEST=ROOT.parents[1]/"outputs"

def keep(p):
    parts=p.relative_to(ROOT).parts
    if any(item in {"__pycache__",".git","mirrors","content_mirrors","transfer_mirrors","exposure_mirrors","temp"} for item in parts):
        return False
    if parts[0]=="report" and ("final" in parts or "preview" in parts):
        return False
    if p.suffix.lower() in {".pyc",".gguf",".zip",".exe",".dll",".parquet"}:
        return False
    return p.name not in {"publication.json","evidence_manifest.json"}

def main():
    files=[]
    # Walk top-down so bare packs and office temporaries are never enumerated or read.
    for parent,folders,names in ROOT.walk():
        folders[:]=[d for d in folders if keep(parent/d)]
        files.extend(parent/n for n in names if keep(parent/n))
    files=sorted(files)
    manifest={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in files}
    m=ROOT/"evidence_manifest.json"
    m.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    name=DEST/"graph-memory-round1-records.zip"
    with ZipFile(name,"w",ZIP_DEFLATED,compresslevel=6) as z:
        for p in [*files,m]:
            z.write(p,p.relative_to(ROOT).as_posix())
    with ZipFile(name) as z:
        assert not z.testzip()
        for key,expected in manifest.items():
            assert sha256(z.read(key)).hexdigest()==expected,key
    out={"files_checked":len(files),"archive":str(name),"size":name.stat().st_size,
         "sha256":sha256(name.read_bytes()).hexdigest(),"manifest_sha256":sha256(m.read_bytes()).hexdigest()}
    (ROOT/"publication.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(json.dumps(out))
if __name__=="__main__":main()

