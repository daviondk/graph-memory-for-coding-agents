"""Install or verify unchanged upstream stage-1 dependencies at the declared revision."""
import hashlib
import json
from pathlib import Path
from fetch_history import BASE, get_bytes

ROOT=Path(__file__).resolve().parent
COMMIT="7152cf96809b45343ccc1caf7115a7d3fa43f956"
REMOTE=f"https://raw.githubusercontent.com/AlibabaResearch/DAMO-ConvAI/{COMMIT}/VibeMemBench/"
FILES=["LICENSE","scripts/run_memory.py","scripts/memory_interface.py","scripts/memory_systems/__init__.py",
       "scripts/memory_systems/demo.py","scripts/CONTRACT.md"]


if __name__=="__main__":
    hashes={}
    for name in FILES:
        expected=get_bytes(REMOTE+name)
        target=BASE/name
        if not target.exists():
            target.parent.mkdir(exist_ok=True,parents=True)
            target.write_bytes(expected)
        if target.read_bytes()!=expected:
            raise ValueError("Upstream bytes differ at "+name)
        hashes[name]=hashlib.sha256(expected).hexdigest()
    (ROOT/"upstream_sha256.json").write_text(json.dumps(hashes,indent=2),encoding="utf8")
    print("Verified",len(hashes),"files at",COMMIT)
