"""Publish the inspected Word and PDF and record their hashes."""
from pathlib import Path
import hashlib
import json
import shutil
from datetime import datetime, timezone
here = Path(__file__).resolve().parent
root = here.parents[2]
qa = json.loads((here/"final/qa.json").read_text(encoding="utf8"))
numeric = json.loads((here/"final/numeric_audit.json").read_text(encoding="utf8"))
assert len(qa["pages"]) == len(list((here/"pages").glob("*.md"))) == 11
assert set(numeric) == {"A2","B","B3","C","D","E","F","F-token"}
dest = root/"outputs"
dest.mkdir(exist_ok=True)
hashes = {}
for ext in ["docx","pdf"]:
    src = here/"final"/("graph-memory-research-round2."+ext)
    target = dest/src.name
    shutil.copy2(src,target)
    hexdigest = hashlib.sha256(src.read_bytes()).hexdigest()
    assert hexdigest == hashlib.sha256(target.read_bytes()).hexdigest()
    hashes[ext] = {"path": str(target.resolve()),"bytes":src.stat().st_size,"sha256":hexdigest}
(here/"final/released.json").write_text(json.dumps({"published_at":datetime.now(timezone.utc).isoformat(),
   "pages":len(qa["pages"]),"links":len(qa["links"]),"quantitative_checks":list(numeric),"outputs":hashes},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("published",[(k,v["bytes"],v["sha256"]) for k,v in hashes.items()])
