"""Verify fixed hashes, action receipts, frozen patches and the independent native test outcomes."""
import collections,gzip,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
def sha(x):return hashlib.sha256(x).hexdigest()
def read(p):return json.loads((D/p).read_bytes())
def facts():
    plan=read("plan.json");seal=read("solve-seal.json");pack=read("packets.json")
    assert sha((D/"plan.json").read_bytes())==seal["base_plan"] and sha((D/"pack-seal.json").read_bytes())==seal["prefix"]
    assert sha((D/"gateway.py").read_bytes())==plan["gateway"] and sha((D/"SOLVER_PROMPT.md").read_bytes())==seal["common_prompt"]
    scout_bytes=gzip.decompress((D/"scout-log.jsonl.gz").read_bytes())
    assert sha(scout_bytes)==read("pack-seal.json")["scout_log"]
    out={}
    for code,arm in plan["roles"].items():
        official=read(code+"-grade.json")
        diff=(D/(code+".diff")).read_bytes()
        receipts=gzip.decompress((D/(code+"-log.jsonl.gz")).read_bytes())
        records=list(map(json.loads,receipts.splitlines()))
        assert sha(receipts)==seal["arms"][code]["raw_log_sha256"] and sha(diff)==official["patch_sha256"]==seal["arms"][code]["diff_sha256"]
        assert sha((D/(code+"-grade.log")).read_bytes())==official["log_sha256"]
        assert len(pack[code]["text"].encode())==pack[code]["size"] and sha(pack[code]["text"].encode())==pack[code]["sha256"]
        assert len(records)<=18 and len(official["parsed_statuses"])==62 and official["complete_observation"]
        before=[]
        for row in records:
            if row["action"]=="edit" and not row["output"].startswith("ERROR "):break
            before.append(row)
        counts=dict(collections.Counter(r["action"] for r in records))
        out[arm]=dict(actions=len(records),counts=counts,visible_bytes=sum(r["bytes"] for r in records),patch_bytes=len(diff),
            memory_bytes=pack[code]["size"],invalid_actions=sum(r["output"].startswith("ERROR ") for r in records),
            before_first_edit=len(before),returned_before_first_edit=sum(r["bytes"] for r in before),
            fail_to_pass=official["fail_to_pass"],pass_to_pass=official["pass_to_pass"],all_pass=official["passed_match"])
    return out
if __name__=="__main__":
    result=facts()
    if (D/"results.json").exists():assert result==read("results.json")["outcomes"]
    print(result)

