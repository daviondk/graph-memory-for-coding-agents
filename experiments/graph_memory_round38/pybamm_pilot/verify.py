"""Verify the sealed treatments, diffs, returned tool events and independent grader logs."""
import gzip
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

D=Path(__file__).resolve().parent
def digest(blob):
    return hashlib.sha256(blob).hexdigest()
def sha(p):
    return digest(p.read_bytes())
def read(p):
    return json.loads(p.read_bytes())

def measure():
    solve=read(D/"solve-seal.json");pack=read(D/"pack-seal.json");plan=read(D/"plan.json")
    assert solve["prefix"]==sha(D/"pack-seal.json") and solve["base_plan"]==pack["plan"]==sha(D/"plan.json")
    assert solve["common_prompt"]==sha(D/"SOLVER_PROMPT.md") and pack["packets"]==sha(D/"packets.json")
    packets=read(D/"packets.json")
    scores={}
    for code,v in solve["arms"].items():
        p=packets[code];assert p["arm"]==plan["roles"][code]==v["arm"]
        assert len(p["text"].encode())==p["size"]==v["memory_bytes"] and digest(p["text"].encode())==p["sha256"]
        raw=gzip.decompress((D/(code+"-log.jsonl.gz")).read_bytes())
        rows=[json.loads(x) for x in raw.splitlines()]
        assert digest(raw)==v["raw_log_sha256"] and v["actions"]==len(rows)<=18
        assert [e["index"] for e in rows]==list(range(1,1+len(rows)))
        assert v["displayed_bytes"]==sum(z["bytes"] for z in rows)
        gr=D/"grades";grade=read(gr/(code+".json"))
        assert grade["patch_sha256"]==v["diff_sha256"]==sha(D/(code+".diff"))
        assert grade["log_sha256"]==sha(gr/(code+".log")) and grade["junit_sha256"]==sha(gr/(code+".xml"))
        assert grade["complete_observation"] and grade["paper_optional_packages"]
        xml=ET.parse(gr/(code+".xml")).getroot()
        cases=xml.findall(".//testcase")
        assert len(cases)==len(grade["junit_statuses"]) and all(t.find("failure") is None and t.find("error") is None for t in cases)
        assert sum(t.find("skipped") is None for t in cases)==sum(z=="PASSED" for z in grade["native_statuses"].values())==8
        scores[v["arm"]]=dict(f2p=grade["fail_to_pass"],p2p=grade["pass_to_pass"],official_exact=grade["official_exact_passed_match"],
            bytes_displayed=v["displayed_bytes"],memory_bytes=p["size"],actions=len(rows),first_edit=next(e["index"] for e in rows if e["action"]=="edit"),
            blocked_public_tests=sum(e["action"]=="test" and "Missing required plugins" in e["output"] for e in rows),tool_counts=v["tool_counts"],patch_sha256=v["diff_sha256"])
    assert len({v["patch_sha256"] for v in scores.values()})==3
    return dict(instance="pybamm-team__pybamm-4267",solvers=3,scout_actions=pack["scout_actions"],arms=scores,
                solver_freeze=sha(D/"solve-seal.json"),packet_freeze=sha(D/"pack-seal.json"))

if __name__=="__main__":
    result=measure()
    assert result==read(D/"results.json")
    if (D/"manifest.json").exists():
        for name,expected in read(D/"manifest.json")["files"].items():assert sha(D/name)==expected,name
    print({k:(v["official_exact"],v["f2p"],v["p2p"],v["first_edit"]) for k,v in result["arms"].items()})

