"""Verify an extracted archive root. Requires only the Python standard library."""
import hashlib,json
from pathlib import Path
def main():
    root=Path(__file__).resolve().parents[2]; manifest=json.loads((root/"MANIFEST.json").read_bytes())
    for name,meta in manifest["files"].items():
        path=root/name
        if not path.is_file() or path.stat().st_size!=meta["bytes"]:raise ValueError(name)
        with path.open("rb") as f:
            if hashlib.file_digest(f,"sha256").hexdigest()!=meta["sha256"]:raise ValueError(name)
    print("Verified",len(manifest["files"]),"files")
if __name__=="__main__":main()
