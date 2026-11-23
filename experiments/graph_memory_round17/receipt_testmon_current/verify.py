"""Recount every native XML outcome and compare both full-replay environments per assigned cohort."""
import collections
import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def main():
    lock=json.loads((ROOT/"assignment.json").read_bytes())
    assert hashlib.sha256((ROOT/"benchmark.py").read_bytes()).hexdigest()==lock["code_sha"]
    assert hashlib.sha256((ROOT/"PROTOCOL_RU.md").read_bytes()).hexdigest()==lock["protocol"]
    runs=json.loads(gzip.decompress((ROOT/"official-runs.gz").read_bytes()))
    assert [[r["cohort"],r["commit"],r["version"]] for r in runs]==lock["order"]
    pairs=collections.defaultdict(dict)
    for r in runs:
        for stage in ["warm","unchanged","selected","full"]:
            result=r[stage];rows={}
            xml=ET.fromstring(result["xml"])
            for t in xml.iter("testcase"):
                modules,cls=t.get("classname").rsplit(".",1)
                n=modules.replace(".","/")+".py::"+cls+"::"+t.get("name")
                state="fail" if any(child.tag in ("failure","error") for child in t) else "skip" if any(c.tag=="skipped" for c in t) else "pass"
                assert n not in rows;rows[n]=state
            assert rows==result["outcomes"]
        pairs[r["cohort"],r["commit"]][r["version"]]=r
    counts=collections.Counter()
    for (cohort,_),v in pairs.items():
        old=v["2.3.0"];recent=v["2.3.1"]
        assert old["warm"]["outcomes"]==recent["warm"]["outcomes"]
        assert old["full"]["outcomes"]==recent["full"]["outcomes"]
        counts[cohort+"_changed_selections"]+=len(set(old["selected"]["outcomes"])^set(recent["selected"]["outcomes"]))
    summary={"native_processes":4*len(runs),"conditions":len(runs),"source_commits":len(pairs),"difference":counts}
    (ROOT/"verification.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf8");print(summary)
if __name__=="__main__":main()
