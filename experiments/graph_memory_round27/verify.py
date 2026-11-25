"""Validate only completed studies listed in the released snapshot."""
import hashlib
import json
from pathlib import Path
import runpy
ROOT=Path(__file__).resolve().parent
def verify():
    studies=json.loads((ROOT/"release.json").read_bytes())["completed"]
    for name in studies:
        base=ROOT/name
        manifest=next(p for p in (base/"manifest.json",base/"MANIFEST_SHA256.json") if p.exists())
        obj=json.loads(manifest.read_bytes())
        files=obj.get("files",obj)
        if isinstance(files,list):
            files={r["name"]:r["sha256"] for r in files}
        for path,digest in files.items():
            p=(base/path).resolve()
            assert p.is_relative_to(base) and hashlib.sha256(p.read_bytes()).hexdigest()==digest,p
    assert runpy.run_path(str(ROOT/"write_cost/verify_cost.py"))["verify"]()==624
    directory=ROOT/"worker_cache"
    assert runpy.run_path(str(directory/"analyse.py"))["compute"]()==json.loads((directory/"results.json").read_bytes())
    runpy.run_path(str(directory/"reuse_distance.py"))["verify"]()
    return len(studies)
if __name__=="__main__":
    print("Verified completed studies",verify())

