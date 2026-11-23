"""Create or independently verify a file inventory without traversing the Git object mirrors."""
import argparse
import hashlib
import json
from pathlib import Path
D=Path(__file__).resolve().parent
MANIFEST=D/"MANIFEST_SHA256.json"

def inventory():
    files=[p for p in D.iterdir() if p.is_file() and p!=MANIFEST]
    for name in ("pr_refs","blobs"):
        files.extend(p for p in (D/name).iterdir() if p.is_file())
    return {p.relative_to(D).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--write",action="store_true");args=parser.parse_args()
    rows=inventory()
    if args.write:MANIFEST.write_text(json.dumps(rows,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf8")
    assert rows==json.loads(MANIFEST.read_bytes())
    print(len(rows),"files;",sum((D/r).stat().st_size for r in rows),"bytes; manifest SHA256",hashlib.sha256(MANIFEST.read_bytes()).hexdigest())

if __name__=="__main__":main()
