"""Verify the SHA256 manifest from an extracted archive using the standard Python library."""
import hashlib,json
from pathlib import Path
def main():
    root=Path(__file__).resolve().parents[2];manifest=json.loads((root/"MANIFEST.json").read_bytes())
    for n,v in manifest["files"].items():
        p=root/n;assert p.is_file() and p.stat().st_size==v["bytes"],n
        with p.open("rb") as f:assert hashlib.file_digest(f,"sha256").hexdigest()==v["sha256"],n
    print(len(manifest["files"]),"verified files")
if __name__=="__main__":main()
