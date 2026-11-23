"""Check upstream digests, sealed predictions, new JUnit and original node IDs without running pytest."""
import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def read(n):
    b=(ROOT/n).read_bytes()
    return json.loads(gzip.decompress(b) if n.endswith(".gz") else b)
def digest(b):return hashlib.sha256(b).hexdigest()
def xml_cases(run):
    result={}
    for r in ET.fromstring(run["xml"]).iter("testcase"):
        mod,cls=r.get("classname").rsplit(".",1)
        node=mod.replace(".","/")+".py::"+cls+"::"+r.get("name")
        assert node not in result
        result[node]="fail" if any(c.tag in ("error","failure") for c in r) else "skip" if r.find("skipped") is not None else "pass"
    assert result==run["nodes"]
    return result
def main():
    inputs=read("auto-input-lock.json")
    original=read("colorama-lock.json")
    for seal in (inputs["files"],read("auto-forecast-seal.json"),original["files"]):
        assert all(digest((ROOT/f).read_bytes())==h for f,h in seal.items())
    for f,h in original["inputs"].items():
        blob=subprocess.check_output(["git","-C","D:/CodexResearch/x20-r17-real-bindings","show",inputs["commit"]+":"+f])
        assert digest(blob)==h
    prior=read("colorama-plan.json");forecasts=read("auto-forecasts.json");data=read("auto-runs.gz")
    old=read("colorama-runs.gz");summary=read("auto-results.json")
    warm=xml_cases(read("auto-warm.gz")["native"])
    assert set(warm.values())=={"pass"} and set(forecasts)==set(data)==set(inputs["variant_sha"])
    total=checked=miss=0
    for oid,run in data.items():
        label=run["label"];actual=xml_cases(run["full"])
        assert actual.keys()==warm.keys() and set(forecasts[oid]["nodeids"])==set(prior[label]["bindings"])
        selected=xml_cases(run["selected"]) if run["selected"] else {}
        assert set(selected)==set(forecasts[oid]["nodeids"]) and all(actual[k]==v for k,v in selected.items())
        failures={k for k,v in actual.items() if v=="fail"}
        assert failures==set(old[label]["failed"]) and oid==old[label]["changed_digest"]
        assert summary["cases"][label]["caught"]==len(failures&selected.keys()) and not failures-selected.keys()
        total+=len(actual);checked+=len(selected);miss+=len(failures-selected.keys())
    print("eligible pairs",total,"actual selected",checked,"missed failures",miss)
if __name__=="__main__":main()
