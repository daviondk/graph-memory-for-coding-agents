"""Record receipt for public R38 artifacts; leave runtime and all solver episodes outside."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inventory():
    files=[p for p in ROOT.iterdir() if p.is_file() and p.name!="manifest.json"]
    files+=list((ROOT/"logs").glob("*"))
    return {p.relative_to(ROOT).as_posix():{"bytes":p.stat().st_size,"sha256":digest(p)} for p in sorted(files)}
if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--check",action="store_true"); a=ap.parse_args()
    path=ROOT/"manifest.json"; now=inventory()
    if a.check:
        expected=json.loads(path.read_text(encoding="utf8"))
        assert now==expected["files"],"artifact set or SHA mismatch"
        inputs=json.loads((ROOT/"history.json").read_text(encoding="utf8"))
        assert digest(ROOT/"memory-packet.txt")==inputs["allowed_sha"]
        print("Verified",len(now),digest(path))
    else:
        path.write_text(json.dumps({"format":"sha256+bytes v1","scope":"calibration and blind input provenance","files":now},ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf8")
        print("Manifest",len(now),digest(path))
