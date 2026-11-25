"""Fetch immutable encoder files and the public data archive; refuse a different checksum."""
from pathlib import Path
import hashlib
import json
import os
import urllib.request

HERE=Path(__file__).resolve().parent
CACHE=Path(os.environ.get("MD2D_CACHE","D:/CodexResearch/x20-r23-multidoc2dial"))
CACHE.mkdir(exist_ok=True,parents=True)
MODEL=CACHE/"model"
MODEL.mkdir(exist_ok=True)
lock=json.loads((HERE/"input-lock.json").read_bytes())
base="https://huggingface.co/intfloat/e5-small-v2/resolve/"+lock["revision"]+"/"
entries=[(MODEL/f,base+("onnx/" if f.endswith(".onnx") else "")+f,h) for f,h in lock["model_files"].items()]
entries.append((CACHE/"source.zip",lock["source_url"],lock["source"]))
for target,url,want in entries:
    raw=target.read_bytes() if target.exists() else urllib.request.urlopen(url,timeout=75).read()
    if hashlib.sha256(raw).hexdigest()!=want:raise ValueError(f"Source mismatch for {target.name}")
    if not target.exists():target.write_bytes(raw)
    print("verified",target.name)
