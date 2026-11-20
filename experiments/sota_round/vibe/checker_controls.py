"""Calibrate the scorer with the release's solution and a nonfunctional-marker patch, outside the solver."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import pyarrow.parquet as pq

here=Path(__file__).resolve().parent
root=Path(os.environ["VIBE_RELEASE"])
targets=[t["instance_id"] for t in json.loads((here/"cohort.json").read_text())["targets"]]
rows=pq.read_table(root/"benchmark"/"test.parquet",filters=[("instance_id","in",targets)]).to_pylist()
marker='diff --git a/.vibe-calibration-marker b/.vibe-calibration-marker\nnew file mode 100644\n--- /dev/null\n+++ b/.vibe-calibration-marker\n@@ -0,0 +1 @@\n+calibration\n'

def control(pair):
    row,arm=pair
    root_out=root.parent/"solver-runtime"/"calibration"/row["instance_id"]/arm
    root_out.mkdir(parents=True,exist_ok=True)
    spec=dict(row)
    if arm=="marker":spec["patch"]=marker
    (root_out/"input.json").write_text(json.dumps([spec]),encoding="utf8")
    proc=subprocess.run([sys.executable,str(here/"wsl_eval.py"),"--json",str(root_out/"input.json"),
        "--max-workers","1","--report-json",str(root_out/"report.json")],cwd=root_out,capture_output=True,text=True)
    (root_out/"execution.log").write_text((proc.stdout or "")+(proc.stderr or ""),encoding="utf8")
    report=json.loads((root_out/"report.json").read_text())["items"][0]
    return {"target":row["instance_id"],"control":arm,"returncode":proc.returncode,"passed_match":report.get("passed_match"),
        "confirmed_F2P":len(report.get("from_fail_to_pass",[])),"lost_P2P":len(report.get("failed_from_pass_to_pass",[])),
        "expected_F2P":len(row["FAIL_TO_PASS"]),"expected_P2P":len(row["PASS_TO_PASS"]),
        "error":report.get("error"),"test_log_bytes":(root_out / report["log_path"]).stat().st_size if report.get("log_path") else None}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(control,[(r,a) for r in rows for a in ["gold","marker"]]))
(here/"checker_controls.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf8")
print(results)
