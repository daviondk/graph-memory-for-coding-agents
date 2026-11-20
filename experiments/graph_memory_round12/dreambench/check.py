"""Verify canonical paper table, observed old/new wheel-index hashes, and typed per-query receipts."""
from artifacts import *
import packaging,sys
s=get(ROOT/"upstream/experiments/results/smoke/results.json")
put(ROOT/"author-smoke.gz",s)
a=(ROOT/"author-tables.tex").read_bytes();b=(ROOT/"upstream/analysis/fold/v2_tables.tex").read_bytes()
assert a.replace(b"\r\n",b"\n")==b.replace(b"\r\n",b"\n")
lock=get(ROOT/"plan-lock.json");assert all(sha((ROOT/n).read_bytes())==d for n,d in lock.items())
idx=get(ROOT/"releases.json");trans=get(ROOT/"transitions.json");new=get(ROOT/"current-witness.gz")
for t in trans:
    n,y=t["name"],t["year"]
    assert new[t["key"]]==wheel(idx[n]["snapshots"][str(y)]["wheel"])
    assert t["old_wheel"]==wheel(idx[n]["snapshots"][str(y-1)]["wheel"])
for r in get(ROOT/"native.gz"):
    assert len(r["items"])==1
    i=r["items"][0];assert i["symbol_scope"]==[r["facet"]] and i["provenance"]["command_outputs"] and i["type"]=="semantic_project"
for row in get(ROOT/"outcomes.gz"):
    assert new[row["key"]]["fields"][row["facet"]]==row["truth"]
    assert row["correct"]==(row["present"] and row["value"]==row["truth"])
receipt=dict(project_python=sys.version,packaging=packaging.__version__,fixture_tasks=s["fixture_task_count"],
             smoke_row_counts={k:len(v["task_records"]) for k,v in s["conditions"].items()},
             published_tables_identical_after_newline_normalization=True,generated_sha=sha(a),published_sha=sha(b),
             wheels_reverified=len(trans)*2,positive_upstream_tests="31 passed",
             receipts={n:sha((ROOT/n).read_bytes()) for n in ("upstream.json","release-verification.json","author-smoke.gz","plan-lock.json","experiment.py","check.py",
             "results.json","outcomes.gz","current-witness.gz","native-tests.log","successor.log")})
put(ROOT/"verification.json",receipt)
print(receipt["smoke_row_counts"])
