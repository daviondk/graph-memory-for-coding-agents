"""Independently reconcile the receipts against every native test's JUnit outcome."""
import collections
import gzip
import hashlib
import json
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
def read(name):
    p=ROOT/name;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def verify_run(run):
    xml={}
    for c in ET.fromstring(run["junit"]).iter("testcase"):
        modules,cls=c.get("classname").rsplit(".",1)
        key=modules.replace(".","/")+".py::"+cls+"::"+c.get("name")
        assert key not in xml
        xml[key]="fail" if c.find("failure") is not None or c.find("error") is not None else "skip" if c.find("skipped") is not None else "pass"
    hooked={}
    for key,row in run["native"]["rows"].items():
        phases=row["phases"]
        hooked[key]="fail" if "failed" in phases.values() else "skip" if "skipped" in phases.values() else "pass"
        assert "failed" in phases.values() or "skipped" in phases.values() or set(phases)=={"setup","call","teardown"}
    assert xml==hooked,(xml,hooked)
    return xml
def main():
    counts=collections.Counter()
    locks=["rollback-lock.json","rollback-forecast-seal.json","testmon-forecast-seal.json","graph-action-lock.json"]
    if (ROOT/"forecast-seal.json").exists():locks.append("forecast-seal.json")
    for name in locks:
        for n,h in read(name).items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    regs=read("testmon-warm.gz");sel={r["commit"]:r for r in read("testmon-runs.gz")};graph=read("graph-actions.gz")
    assert regs.keys()==sel.keys()==graph.keys()
    for commit in regs:
        a=regs[commit];b=sel[commit];g=graph[commit]
        old=verify_run(a["pure_child"]);assert old==verify_run(a["warm"])==verify_run(g["initial"])
        assert not verify_run(a["unchanged"])
        tr=verify_run(b["replay"][0]);assert tr==verify_run(b["replay"][1]) and old.keys()==tr.keys()
        t=verify_run(b["selected"]);gr=verify_run(g["final"]) if g["final"] else {}
        assert all(tr[k]==v for k,v in t.items()) and all(tr[k]==v for k,v in gr.items())
        assert set(gr)==set(g["choose"])
        counts.update({"commits":1,"total":len(old),"testmon":len(t),"graph":len(gr),"failure":sum(v=="fail" for v in tr.values()),"testmon_false_pass":sum(v=="fail" and k not in t for k,v in tr.items()),"graph_false_pass":sum(v=="fail" and k not in gr for k,v in tr.items())})
    rows=read("rollback-graded.gz")
    assert all(r["repeats"]==[r["actual"],r["actual"]] for r in rows)
    assert counts["total"]==len(rows)
    print(json.dumps(counts,sort_keys=True))
if __name__=="__main__":main()
