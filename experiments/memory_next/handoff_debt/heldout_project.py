"""Resolve r02/r03 grades after policy assignments are sealed."""
from pathlib import Path
import hashlib
import json
from assign import dump
from download import ROOT,CACHE,pq
if __name__=="__main__":
    for n,h in json.loads((ROOT/"heldout_predictions_lock.json").read_text(encoding="utf-8")).items():
        assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    rows=[]
    for p in sorted(CACHE.glob("*.parquet")):
        cols=["run_id","attempt","validation_json","summary_json","validation_passed","agent_events","prompt_tokens","agent_seconds","source_summary_sha256"]
        for r in pq.read_table(p,columns=cols).to_pylist():
            if r["attempt"] not in ("r02","r03"):continue
            v=json.loads(r["validation_json"]) if r["validation_json"] else {};s=json.loads(r["summary_json"]) if r["summary_json"] else {}
            y=s.get("official_resolved")
            assert y is None or isinstance(y,bool)
            rows.append({"run_id":r["run_id"],"official_known":int(v.get("backend")=="swebench_official" and isinstance(y,bool)),
                         "official_resolved":None if y is None else int(y),"backend":v.get("backend"),
                         "passed":None if r["validation_passed"] is None else int(r["validation_passed"]),
                         **{k:r[k] for k in ["agent_events","prompt_tokens","agent_seconds","source_summary_sha256"]}})
    assert len(rows)==len({r["run_id"] for r in rows})==320
    dump(ROOT/"heldout_outcomes.csv",rows)

