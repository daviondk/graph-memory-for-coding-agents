"""Extra permitted maintenance time on this replay; no new runtime assumption about actual writes."""
import json,gzip
from collections import defaultdict
from pathlib import Path
D=Path(__file__).resolve().parent;P=D.parent/"published/external"
def rows(p):
    with gzip.open(p,"rt",encoding="utf8") as stream:yield from map(json.loads,stream)
last=defaultdict(int)
for q in rows(P/"queries.jsonl.gz"):
    if q["kind"]=="edit":last[q["id"]]=max(last[q["id"]],q["t"])
steps=sum(sum(e["step"]<=last[s["id"]] for e in s["events"]) for s in rows(P/"symmetric_stream.jsonl.gz"))
data=json.loads((D/"native_results.json").read_bytes())["all"]["sum_ms"];gain=data[0]-data[1]
obj={"queries":186,"tasks":len(last),"steps_through_last_measured_query":steps,"read_ms_saved":gain,"allowable_extra_mean_ms_per_step":gain/steps,"denominator":"all observed steps through last measured query of each of 48 edit trajectories; several later steps omitted"}
(D/"breakeven.json").write_text(json.dumps(obj,indent=1));print(json.dumps(obj))

