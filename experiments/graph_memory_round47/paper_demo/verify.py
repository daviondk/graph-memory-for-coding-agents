"""Check the standalone files, measured demo case, and traceable SQL projection."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json
import sqlite3
import subprocess
import sys
root = Path(__file__).resolve().parent
def digest(data):
    return sha256(data).hexdigest()
receipt = json.loads((root/"CONTENT_SHA256.json").read_bytes())
check = json.loads((root/"build-check.json").read_bytes())
with ZipFile(root/"candidate.zip") as archive:
    assert archive.testzip() is None
    assert set(archive.namelist()) == set(receipt) | {"CONTENT_SHA256.json"}
    for path, expected in receipt.items():
        assert digest(archive.read(path)) == expected == digest((root/path).read_bytes())
assert digest((root/"paper.pdf").read_bytes()) == check["pdf_sha256"]
assert digest((root/"candidate.zip").read_bytes()) == check["zip_sha256"]
video = json.loads((root/"browser-video.json").read_bytes())
assert len(video["scenes"]) == 10 and "Together they change" in video["scenes"][-1][1]
assert video["bytes"] == (root/"walkthrough.mp4").stat().st_size and video["seconds"] == 148.8
dbpath = root/"apps/trace/runtime/planes.sqlite"
with sqlite3.connect(dbpath.resolve().as_uri()+"?mode=ro", uri=True) as db:
    assert db.execute("SELECT count(*) FROM plane").fetchone()[0] == 10927
upstream = root.parent/"joint_packets/planes.sqlite"
if upstream.is_file():
    assert digest(dbpath.read_bytes()) == digest(upstream.read_bytes())
subprocess.run([sys.executable,"-B",str(root/"verify_candidate.py")],check=True)
print("Verified four-page build receipt, ten recorded scenes, SQLite source and standalone archive.")
