"""Verify executable and distributions of the common 3.11 validation environment."""
from pathlib import Path
import importlib.metadata as md
import hashlib
import json
import sys
D=Path(__file__).resolve().parent
v=Path("D:/CodexResearch/x20-round9-test311-runtime/venv/Scripts/python.exe")
assert Path(sys.executable).resolve()==v.resolve() and sys.version_info[:3]==(3,11,15)
raw=(D/"runtime-freeze.txt").read_bytes()
packages=dict(r.split("==",1) for r in raw.decode("utf-8-sig").splitlines() if r.strip())
assert packages.get("py")=="1.11.0" and all(md.version(k)==ver for k,ver in packages.items())
import py
assert py.test is not None
receipt=dict(interpreter=sys.executable,version=sys.version,freeze_sha256=hashlib.sha256(raw).hexdigest(),
             distributions=packages,py_file=py.__file__)
(D/("runtime-"+sys.argv[1]+".json")).write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf8")
