from pathlib import Path
from collections import Counter
import json
import sys
import hashlib

ROOT=Path(__file__).resolve().parent
def load(name):return json.loads((ROOT/name).read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def check():
    manifest={p.name:sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!="MANIFEST_SHA256.json"}
    if "--write-manifest" in sys.argv:
        (ROOT/"MANIFEST_SHA256.json").write_bytes((json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode())
    assert manifest==load("MANIFEST_SHA256.json")
    design=load("design-lock.json");fc=load("forecast-seal.json");l=load("input-lock.json")
    assert design["script"]==manifest["study.py"] and design["protocol"]==manifest["PROTOCOL_RU.md"]
    assert l["design"]==manifest["design-lock.json"] and fc["input"]==manifest["input-lock.json"] and fc["sha"]==manifest["forecast.json"]
    by={r["id"]:r for r in load("forecast.json")};truth=load("outcomes.json");s=load("results.json")
    assert {r["id"] for r in design["roster"]}==set(by)=={r["id"] for r in truth}
    assert len({(r["repo"],r["iid"]) for r in design["roster"]})==len(by)
    assert Counter(x["label"] for x in truth)==s["counts"]
    for r in truth:
        for arm,forecast in by[r["id"]]["arms"].items():
            out=forecast["choice"];valid=(out is None and r["label"]=="clean") or (out in r["actual"] and r["label"]=="failed")
            assert valid==r["scores"][arm]
    for arm,vals in s["by"].items():assert sum(r["scores"][arm] for r in truth)==vals["total"]
    print("OK",len(manifest),"files",len(by),"archived handoffs")

if __name__=="__main__":check()
