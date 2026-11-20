"""Publish byte-identical QA-verified files to outputs."""
import hashlib
import json
from pathlib import Path
from shutil import copyfile

here = Path(__file__).resolve().parent
final = here / "final"
out = here.parents[2] / "outputs"
provenance = json.loads((final / "numeric_audit.json").read_text("utf8"))
qa = json.loads((final / "qa.json").read_text("utf8"))
assert len(qa["pages"]) == len(list((here / "pages").glob("*.md")))
assert provenance["checked_values"] >= 130
out.mkdir(exist_ok=True)
receipts = []
for ext in ("docx", "pdf"):
    name = f"graph-memory-research-round3.{ext}"
    source = final / name
    target = out / name
    copyfile(source, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    assert digest == hashlib.sha256(source.read_bytes()).hexdigest()
    receipts.append({"file":name,"bytes":target.stat().st_size,"sha256":digest})
(final / "published.json").write_text(json.dumps(receipts,indent=2),encoding="utf8")
print(receipts)
