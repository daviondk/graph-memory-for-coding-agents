import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

d=Path(__file__).resolve().parent
raw=(d/"outcomes.json.gz").read_bytes()
rows=json.loads(gzip.decompress(raw))
result=json.loads((d/"results.json").read_bytes())
assert hashlib.sha256(raw).hexdigest()==result["output"]
for pct,g in result["groups"].items():
    events=[r for q in rows.values() for r in q[pct]["queries"]]
    assert len(events)==g["events"] and sum(r["stable"] for r in events if r["added"])==g["stable"]
    assert Counter(r["mode"] for r in events)==g["modes"]
    assert all(r["stable"] for r in events if r["mode"] in ("strict_certificate","no_open_candidate"))
    assert all(len(r["full_ns"])==len(r["update_ns"])==3 for r in events)
    assert g["time_ratio"]==sum(sum(r["full_ns"]) for r in events)/sum(sum(r["update_ns"]) for r in events)
print("Verified",sum(g["events"] for g in result["groups"].values()),"arrivals")

