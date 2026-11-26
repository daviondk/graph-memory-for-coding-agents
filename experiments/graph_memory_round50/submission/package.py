"""Assemble the offline demo from the R49 runtime and the signed two-read replay."""
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import json
import sqlite3

ROOT = Path(__file__).resolve().parent
ARCHIVE_R49 = "4f418c3f88b6124f3813f0ba528dbbde1646bb0a2594b40cd1f0cab2aebd3028"
GATE_MANIFEST = "2737806037fe0f85ee04431bce15963f59c3c5bbbb9841e39bf4ab1cd9b22b2c"
ADDRESS_MANIFEST = "9eaef6282ed1a97ef613e658c593e5e83f490f57ddb8d68daf050c39b0c47cfc"
OVERRIDES = ("paper.tex", "paper.pdf", "sources.bib", "README.md", "demo.py", "start.html", "verify_candidate.py")
ADDRESS = ("address_server.py", "index.html", "address.sqlite")


def hashed(blob):
    return sha256(blob).hexdigest()


def inventory(receipts):
    return (json.dumps(receipts, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build(original, projected, target):
    assert hashed(original.read_bytes()) == ARCHIVE_R49
    with ZipFile(original) as z:
        files = {n: z.read(n) for n in z.namelist()}
    receipt = json.loads(files.pop("CONTENT_SHA256.json"))
    assert {n: hashed(data) for n, data in files.items()} == receipt
    signed = (projected / "manifest.json").read_bytes()
    assert hashed(signed) == ADDRESS_MANIFEST
    entries = json.loads(signed)["files"]
    for name in ADDRESS:
        data = (projected / name).read_bytes()
        assert hashed(data) == entries[name]
        files["apps/address/" + name] = data
    uri = (projected/"address.sqlite").resolve().as_uri()+"?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as db:
        metadata = dict(db.execute("SELECT key,value FROM metadata"))
        assert metadata["manifest"] == GATE_MANIFEST and int(metadata["count"]) == 1280
    for name in OVERRIDES:
        files[name] = (ROOT / name).read_bytes()
    files["app-inputs.json"] = inventory({n: hashed(v) for n, v in files.items() if n.startswith("apps/")})
    files["CONTENT_SHA256.json"] = inventory({n: hashed(v) for n, v in files.items()})
    assert len(files) == 51
    with ZipFile(target, "w") as z:
        for name, blob in sorted(files.items()):
            spec = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            spec.compress_type = ZIP_DEFLATED
            spec.external_attr = 0o100644 << 16
            z.writestr(spec, blob)
    print(f"{len(files)} members, SHA-256 {hashed(target.read_bytes())}")


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--base", type=Path, default=ROOT.parents[1]/"graph_memory_round49"/"stream_demo"/"candidate.zip")
    ap.add_argument("--address", type=Path, default=ROOT.parent/"address_demo")
    ap.add_argument("--output", type=Path, default=ROOT/"candidate.zip")
    args = ap.parse_args()
    build(args.base, args.address, args.output)
