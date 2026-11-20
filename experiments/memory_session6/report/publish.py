"""Copy a verified report and record the hashes of the exact released files."""
import hashlib
import json
import shutil
from pathlib import Path

here = Path(__file__).resolve().parent
final = here / "final"
outputs = here.parents[2] / "outputs"
report = "agent-memory-session6-results"
qa = json.loads((final / "qa.json").read_text(encoding="utf-8"))
assert len(qa["pages"]) == len(list((here/"pages").glob("*.md")))
manifest = {}
for ext in [".docx", ".pdf"]:
    source = final / (report + ext)
    out = outputs / source.name
    shutil.copyfile(source, out)
    a = hashlib.sha256(source.read_bytes()).hexdigest()
    b = hashlib.sha256(out.read_bytes()).hexdigest()
    assert a == b
    manifest[out.name] = {"sha256": a, "bytes": out.stat().st_size}
(final/"released.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
