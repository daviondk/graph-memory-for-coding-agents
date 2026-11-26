"""Fetch pinned public code into a local read-only study cache; verify every selected Git blob."""
from pathlib import Path
import hashlib
import io
import json
import requests
import zipfile

HERE=Path(__file__).resolve().parent
REV="5508f8be81025d8aa90726b1e06aef4ea484e577"
CACHE=Path("D:/CodexResearch/x20-r40-memtrace-runtime")/REV


def main():
    tree=json.loads((HERE/"upstream-tree.json").read_bytes())
    assert tree["commit"]==REV
    selected={p:h for p,h in tree["files"].items()
              if p.startswith("src/memtrace/") and p.endswith(".py") or p.startswith("tests/unit/") and p.endswith(".py")
              or p in ("pyproject.toml","README.md","LICENSE")}
    resp=requests.get("https://codeload.github.com/Homy-Xu/MemTrace/zip/"+REV,timeout=30)
    resp.raise_for_status()
    assert len(resp.content)<50_000_000
    CACHE.mkdir(parents=True,exist_ok=True)
    validated={}
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        for name,blobhash in selected.items():
            target=(CACHE/name).resolve()
            assert target.is_relative_to(CACHE.resolve())
            content=archive.read("MemTrace-"+REV+"/"+name)
            assert hashlib.sha1(b"blob "+str(len(content)).encode()+b"\0"+content).hexdigest()==blobhash
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(content)
            validated[name]=hashlib.sha256(content).hexdigest()
    info={"commit":REV,"archive_sha256":hashlib.sha256(resp.content).hexdigest(),"files":validated}
    (HERE/"source-hashes.json").write_text(json.dumps(info,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print("Verified", len(validated),"Git source blobs; source code was not executed.")


if __name__=="__main__":main()
