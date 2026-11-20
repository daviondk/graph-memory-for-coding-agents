"""Independently validate checksums, membership and the released/primary counts on disk."""
import hashlib
import json
import platform
import sys
from collections import defaultdict
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parent
def read(name):
    return json.loads((root/name).read_text(encoding="utf-8"))
for lock in ["registration_parser_fix.json","predictions_lock.json"]:
    for f in read(lock)["files"]:
        assert hashlib.sha256((root/f["name"]).read_bytes()).hexdigest() == f["sha256"].lower()
rows, labels, pred = read("features.json"), read("labels.json"),read("predictions.json")
assert len(rows) == len(labels) == len(pred) == 180
assert set(labels) == set(pred) == {r["id"] for r in rows}
assert len({r["task"] for r in rows})==52 and len({r["project"] for r in rows})==11
tasks = defaultdict(set)
for r in rows:
    assert set(r["x"]) == {"status", "subtype", "responses", "changed_files","changed_functions",
                          "trace_files","trace_functions","changed_trace_files"}
    tasks[r["task"]].add(r["project"])
assert all(len(r)==1 for r in tasks.values())
scores = read("score.json")
for k in pred[rows[0]["id"]]:
    sequence=[labels[r["id"]][pred[r["id"]][k]] for r in rows]
    assert sum(sequence) == scores["results"][k]["solved"]
    assert all(scores["episode_outcomes"][r["id"]][k] == y for r,y in zip(rows,sequence))
assert all(s["n"] == 180 for s in scores["results"].values())
strict = read("sensitivity.json")
assert len(set(strict["complete_checkable_ids"])) == strict["n_fully_checkable"] == 178
assert set(strict["complete_checkable_ids"]) <= set(labels)
report = {"checks":"input and configuration hashes, complete-case counts, instance groups, feature whitelist, outcome recomputation, secondary population",
          "python":sys.version,"numpy":np.__version__,"platform":platform.platform(),"checks_passed":True}
(root/"verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print("R2-D verified")
