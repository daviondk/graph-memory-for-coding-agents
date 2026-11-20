"""Cross-check completed native reports and release hashes without exposing input patches."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
import pyarrow
HERE=Path(__file__).resolve().parent;VIBE=HERE.parent
REL=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
PRIVATE=Path("D:/CodexResearch/x20-r12-evaluator-inputs")
def load(f):return json.loads(f.read_bytes())
def sha(data):return hashlib.sha256(data).hexdigest()
def put(f,data):f.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf8")

def main():
    rows=[]
    for f in sorted([*HERE.glob("controls/*/*/result.json"),*HERE.glob("models/*/*/result.json")]):
        r=load(f);i,m=r["instance"],r["method"];work=PRIVATE/i/m
        assert not work.resolve().is_relative_to(VIBE)
        for name,h in r["hashes"].items():assert sha((f.parent/name).read_bytes())==h
        assert sha(load(work/"eval_input.json")[0]["patch"].encode())==r["patch_sha"]
        d={k:r[k] for k in ["instance","method","status","patch_sha","patch_bytes","source","passed_match","unit_exit","confirmed_F2P","expected_F2P","lost_P2P","expected_P2P","vendor_error"]}
        d["units_bytes"]=(f.parent/"unit.log").stat().st_size if (f.parent/"unit.log").is_file() else None
        unit=f.parent/"unit.log"
        if not unit.is_file():
            d["execution_stage"]="vendor_before_unit_run"
        else:
            log=unit.read_text(encoding="utf8",errors="replace")
            if "no valid patches in input" in log.lower() or ("error: patch" in log.lower() and "test session starts" not in log.lower()):
                d["execution_stage"]="patch_application"
            elif r["unit_exit"]==0 or re.search(r"(?i)(\d+ (?:passed|failed|errors?)|=+ test session starts =+)",log):
                d["execution_stage"]="ran_tests"
            else:
                d["execution_stage"]="check_raw_unit_log"
        d["measured_F2P"]=d["confirmed_F2P"] if d["execution_stage"]=="ran_tests" else None
        d["measured_P2P_lost"]=d["lost_P2P"] if d["execution_stage"]=="ran_tests" else None
        if (f.parent/"native-report.json").is_file():
            item=load(f.parent/"native-report.json")["items"][0]
            assert item.get("passed_match")==r["passed_match"]
            if item.get("log_path"):assert d["units_bytes"] is not None
        if m not in ("gold","marker"):
            finished=VIBE/"episodes/python"/i/m/"seed0/finished.json"
            assert sha(finished.read_bytes())==r["finish_sha"]
        d["output"]=f.relative_to(HERE).as_posix()
        rows.append(d)
    ids=[p["instance_id"] for p in load(VIBE/"cohort.json")["targets"]]
    expected={ (i,m) for i in ids for m in ("gold","marker","base","raw","graph")}
    observed={(r["instance"],r["method"]) for r in rows}
    assert observed<=expected
    manifests={}
    for f in [REL/"scripts/vendor/eval.py",REL/"scripts/vendor/log_parsers.py",REL/"scripts/run_eval.py",REL/"benchmark/test.parquet",VIBE/"cohort.json",HERE/"bin/docker",HERE/"bridge.py",HERE/"grade.py",HERE/"audit.py"]:
        manifests[str(f)]=sha(f.read_bytes())
    output=dict(complete=expected==observed,rows=rows,expected=len(expected),pending=sorted(expected-observed),
                release_files=manifests,pyarrow=pyarrow.__version__,runtime=sys.version)
    put(HERE/"results.json",output)
    print("complete" if output["complete"] else "partial",len(rows),"/",len(expected))
if __name__=="__main__":main()
