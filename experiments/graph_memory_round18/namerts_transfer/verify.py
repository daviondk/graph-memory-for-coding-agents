"""Offline verification of all artifact digests and of the published paired counts."""
from pathlib import Path
import gzip
import hashlib
import json
import sys
root=Path(__file__).resolve().parent
def read(name):
    b=(root/name).read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files():
    return {p.name:digest(p) for p in sorted(root.iterdir()) if p.is_file() and p.name!="MANIFEST_SHA256.json"}
def main():
    if "--write-manifest" in sys.argv:
        (root/"MANIFEST_SHA256.json").write_text(json.dumps(files(),indent=2,sort_keys=True),encoding="utf8")
    assert read("MANIFEST_SHA256.json")==files()
    for seal in ("plan-lock.json","forecast-seal.json","frequency-lock.json","frequency-seal.json","census-lock.json","census-seal.json"):
        for name,h in read(seal).items():assert digest(root/name)==h
    p=read("plan.json")
    earlier=set(p["old_shas"])
    for r in p["cohort"]:
        assert not earlier & {r["current"],r["true_parent"],r["direct_parent"]}
    pairs=read("paired.json");assert len(pairs)==6
    forecasts=read("forecasts.gz");assert len(forecasts)==120 and all(r["clean"] for r in forecasts)
    for r in pairs:
        traces=[s for s in forecasts if s["current"]==r["current"]]
        for k in traces[0]["policies"]:
            assert {s["file"] for s in traces if s["policies"][k]}==set(r["methods"][k]["selected"])
        for stats in r["methods"].values():
            sel=set(stats["selected"]);truth=set(r["truth"])
            assert set(stats["hits"])==sel&truth and set(stats["misses"])==truth-sel
    assert sum(len(r["truth"]) for r in pairs)==36
    assert sum(len(r["methods"]["outer_function"]["selected"]) for r in pairs)==120
    assert sum(len(r["methods"]["NameRTS"]["selected"]) for r in pairs)==50
    full=read("census-results.json")["pairs"][0]
    traces=read("supplemental-forecasts.gz")+read("census-extra-forecasts.gz")
    assert len({r["file"] for r in traces})==48
    assert {r["file"] for r in traces if r["policies"]["outer_function"]}==set(full["methods"]["outer_function"]["selected"])
    assert len(full["methods"]["outer_function"]["selected"])==3
    assert set(full["methods"]["outer_function"]["hits"])==set(full["methods"]["NameRTS"]["hits"])==set(full["truth"])
    assert sum(r["confirmed_same_pass"] for r in read("current-diagnostic.json"))==730
    print("OK",len(files()),"files; six seals; 120 primary file forecasts, 48 in complete mechanism census; 18 current reruns")
if __name__=="__main__":main()
