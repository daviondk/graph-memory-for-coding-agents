"""Construct the conditional search interface using only the source text and donated anchor."""
import gzip
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("CONTRADOC_CACHE", "D:/CodexResearch/x20-contradoc"))
SOURCE = CACHE / "ContraDoc.json"
SOURCE_SHA = "def2213b8c6314353614ddadd0c8bbefeb883a2ccd4ebfcacacf10e8754e158c"
BOUNDARY = re.compile(r"""(?<=[.!?])\s+|(?<=[.!?]["'”’])\s+""")
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def norm(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())
def dump(path, obj):
    raw = (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)
def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)
def build(records):
    packets = []
    reasons = {}
    for doc, row in sorted(records.items()):
        text, anchor = norm(row["text"]), norm(row["evidence"])
        if not anchor or text.count(anchor) != 1:
            reasons[doc] = "anchor absent or ambiguous"
            continue
        before, after = text.split(anchor)
        left = [x.strip() for x in BOUNDARY.split(before) if x.strip()]
        right = [x.strip() for x in BOUNDARY.split(after) if x.strip()]
        if len(left) + len(right) < 2:
            reasons[doc] = "fewer than two other records"
            continue
        addresses = list(range(-len(left), 0)) + list(range(1, len(right) + 1))
        packets.append({"id": doc, "anchor": anchor, "records": list(zip(addresses, left + right))})
    return packets, reasons
def main():
    assert sha(SOURCE.read_bytes()) == SOURCE_SHA
    pos = read(SOURCE)["pos"]
    view = {doc: {k: row[k] for k in ("text", "evidence")} for doc, row in pos.items()}
    packets, reasons = build(view)
    dump(CACHE / "packets.json.gz", packets)
    dump(ROOT / "input-lock.json", {"source": SOURCE_SHA, "packets": sha((CACHE/"packets.json.gz").read_bytes()),
          "all": len(pos), "supplied": len(packets), "excluded": reasons, "protocol": sha((ROOT/"PROTOCOL_RU.md").read_bytes())})
    print("sealed packets", len(packets))
if __name__ == "__main__":
    main()
