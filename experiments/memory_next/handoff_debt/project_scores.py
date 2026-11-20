"""Open only outcomes/costs after freezing all admissible records and the policy."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from download import ROOT,CACHE,pq
from assign import dump

if __name__=="__main__":
    for n,h in json.loads((ROOT/"blind_lock.json").read_text(encoding="utf-8")).items():
        assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    data=[]
    for path in sorted(CACHE.glob("*.parquet")):
        cols=["run_id","attempt","agent_events","prompt_tokens","completion_tokens","agent_seconds","has_validation","has_run_error",
              "validation_passed","validation_json","summary_json","source_summary_sha256"]
        for r in pq.read_table(path,columns=cols).to_pylist():
            if r["attempt"]!="r01":continue
            v=json.loads(r["validation_json"]) if r["validation_json"] else {}
            s=json.loads(r["summary_json"]) if r["summary_json"] else {}
            official=s.get("official_resolved")
            assert official is None or isinstance(official,bool),type(official)
            backend=v.get("backend")
            run_error=r["has_run_error"]
            grade_known=bool(backend=="swebench_official" and isinstance(official,bool))
            data.append({"run_id":r["run_id"],"official_known":int(grade_known),"official_resolved":None if official is None else int(official),
                         "passed":None if r["validation_passed"] is None else int(r["validation_passed"]),"backend":backend,
                         "validation_flag":int(r["has_validation"]),"run_error":int(run_error),"agent_events":r["agent_events"],
                         "prompt_tokens":r["prompt_tokens"],"completion_tokens":r["completion_tokens"],"agent_seconds":r["agent_seconds"],
                         "summary_sha256":r["source_summary_sha256"]})
    assert len({r["run_id"] for r in data})==len(data)==6120
    dump(ROOT/"arm_outcomes.csv",data)
    print("official rows",len(data))

