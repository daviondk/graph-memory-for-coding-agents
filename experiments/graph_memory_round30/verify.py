"""Validate released study files and headline quantities using the measured rows."""
import gzip,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(path):
    p=ROOT/path;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def verify():
    release=read("release.json")
    for name,wanted in release["manifests"].items():
        base=ROOT/name
        p=next(p for p in (base/"manifest.json",base/"MANIFEST_SHA256.json") if p.is_file())
        sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
        assert sha(p)==wanted,p
        content=json.loads(p.read_bytes());files=content.get("files",content)
        if isinstance(files,list):files={f["name"]:f.get("sha",f.get("sha256")) for f in files}
        assert set(files)=={f.relative_to(base).as_posix() for f in base.rglob("*") if f.is_file() and "__pycache__" not in f.parts and f!=p}
        for rel,expected in files.items():
            file=(base/rel).resolve();dig=expected["sha256"] if isinstance(expected,dict) else expected
            assert file.is_relative_to(base) and sha(file)==dig,file
    results=read("statefuse_handoff/results.json");rows=read("statefuse_handoff/outcomes.json.gz")
    for k,v in results["counts"].items():assert sum(r[k] for r in rows.values())==v
    assert len(rows)==400 and results["counts"]["native_both"]==results["counts"]["flat_both"]==400
    policy=read("online_refresh/results.json");events=read("online_refresh/decisions.json.gz")
    assert len(events)==policy["simulations"]==640
    assert all(len(set(e[-1]))==171==len(e[-1]) for e in events)
    receipt=read("receipt_dependencies/results.json")
    assert receipt["structural"]["distinct_masks"]["sum"]==1722 and receipt["strict"]==94464
    swe=read("witness_handoff/swe-results.json")["panel"]["future"]
    ise=read("witness_handoff/ise4-results.json")["panel"]["future"]
    assert (swe["n_cases"],swe["n_pairs"])==(125,225) and ise["n_pairs"]==267
    a=swe["methods"]["distinct_worker"]["one_worker"];b=swe["methods"]["first_two"]["one_worker"]
    assert math.isclose(a-b,swe["paired"]["distinct_worker__first_two"]["one_worker"]["delta"])
    return len(release["completed"])
if __name__=="__main__":print("Verified studies",verify())
