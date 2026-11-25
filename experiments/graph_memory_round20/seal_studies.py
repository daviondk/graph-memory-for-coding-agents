"""Seal public artifacts of the root-run studies; large local caches are external."""
import hashlib
import json
from pathlib import Path
D=Path(__file__).resolve().parent
OWN=("degree_write","online_update","set_writer","dialogue_stream","fine_read","fine_train","fine_lextrain","fine_subset","factor_reader","untuned_holdout")
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def seal(name):
    root=D/name;allowed={".md",".json",".gz",".py",".ps1"}
    files={p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob("*")) if p.is_file() and
        not any(part.startswith((".","__")) for part in p.relative_to(root).parts) and p.suffix in allowed and p.name!="MANIFEST_SHA256.json"}
    assert "REPORT_RU.md" in files
    (root/"MANIFEST_SHA256.json").write_text(json.dumps(files,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8")
if __name__=="__main__":
    for name in OWN:seal(name)
