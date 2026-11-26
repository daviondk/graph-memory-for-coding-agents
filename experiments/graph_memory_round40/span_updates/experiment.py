"""Compare certified retention at two invalidation granularities on frozen plans."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent
NAT = ROOT.parent / "natural_invalidations"
WORK = ROOT.parents[1]
sys.path.insert(0, str(NAT))
from score import select
from project import read, sha


def signed(folder, filename):
    path = folder / filename
    manifest = read(folder / "manifest.json")
    assert sha(path) == manifest.get("files", manifest)[filename]
    return read(path)


def dump(path, obj):
    data = (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if path.suffix == ".gz":
        data = gzip.compress(data, mtime=0)
    path.write_bytes(data)


def differences(rows):
    if not rows:
        return {}
    by_issue = defaultdict(list)
    for row in rows:
        by_issue[row["issue"]].append(row["range_reuse"] - row["file_reuse"])
    means = np.array([np.mean(by_issue[k]) for k in sorted(by_issue)])
    boot = np.random.default_rng(401113).choice(means, (10000, len(means))).mean(axis=1)
    return dict(n=len(rows), issues=len(means), file_reuse=sum(r["file_reuse"] for r in rows),
                range_reuse=sum(r["range_reuse"] for r in rows), stable_addresses=sum(r["same_coords"] for r in rows),
                before_bytes=sum(r["bytes"] for r in rows), surviving_bytes=sum(r["bytes_survive"] for r in rows),
                in_new_packet_bytes=sum(r["bytes_in_new"] for r in rows), macro_pp=float(means.mean()*100),
                ci_pp=(np.quantile(boot,[0.025,0.975])*100).tolist())


def run():
    demand = WORK / "graph_memory_round37/edit_demand"
    pairs = signed(demand, "followup.json.gz")
    receipts = signed(demand, "native_boundaries.json.gz")
    history = signed(demand, "prefixes.json.gz")
    plans = signed(NAT, "plans.json.gz")
    observed = signed(NAT, "observations.json.gz")
    known = {(r["rid"], r["event"]): r for r in observed}
    joins = {(r["rid"], r["edit"]): r for r in pairs}
    results = []
    reasons = Counter()
    for rid, data in receipts.items():
        for event, acknowledgement, op, path in data.get("successful_writes", []):
            before = known.get((rid, event))
            if before is None or not before["present"] or op != "str_replace":
                continue
            pair = joins.get((rid, acknowledgement))
            if pair is None or pair["prefix"] != "clean":
                reasons["missing_clean_pair"] += 1
                continue
            params = history[pair["q"]]
            start, end, delta = (params[k] for k in ("start","end","delta"))
            if start is None:
                reasons["unlocalized"] += 1
                continue
            assert hashlib.sha256(params["path"].encode()).hexdigest() == path == before["actual"]
            blocks = plans[rid][str(event)]
            rows = [(i,b[0],b[3],b[4]) for i,b in enumerate(blocks)]
            deleted = {i for i,(p,lo,hi,*_) in enumerate(blocks) if p == path and lo <= end and hi >= start}
            old,_,_ = select(rows)
            new, head,_ = select([r for r in rows if r[0] not in deleted])
            assert len(old) == before["selected"] and sum(blocks[i][3] for i in old) == before["bytes"]
            exact = deleted.isdisjoint(old) and set(head).issubset(old)
            assert exact == (old == new)
            moved = {i for i,(p,lo,hi,*_) in enumerate(blocks) if p==path and lo>end and delta!=0}
            eligible = [i for i,b in enumerate(blocks) if b[0] == path and i not in deleted]
            survivors = set(old)-deleted
            overlap = set(old)&set(new)
            results.append(dict(rid=rid, event=event, receipt=acknowledgement, view=pair["prev"], path=path,
                    issue=before["issue"], group=before["group"], start=start, end=end, delta=delta,
                    file_reuse=1-before["actual_changed"], range_reuse=int(exact),
                    same_coords=int(exact and moved.isdisjoint(old)), bytes=before["bytes"],
                    bytes_survive=sum(blocks[i][3] for i in survivors), bytes_in_new=sum(blocks[i][3] for i in overlap),
                    eligible=eligible, old=list(old), new=list(new)))
    assert len({(r["rid"],r["event"]) for r in results}) == len(results)
    results.sort(key=lambda r:(r["rid"],r["event"]))
    summary = {name:differences(sub) for name,sub in [
        ("main",[r for r in results if r["group"]=="main"]),("additional",[r for r in results if r["group"]!="main"]),
        ("all",results),("main_changed_length",[r for r in results if r["group"]=="main" and r["delta"]])]}
    for name,keep in [("all",lambda r:True),("main",lambda r:r["group"]=="main")]:
        sub=[r for r in observed if keep(r)]
        summary[name]["attempts"]=len(sub)
        summary[name]["present_attempts"]=sum(r["present"] for r in sub)
        summary[name]["file_unchanged_all_attempts"]=sum(1-r["actual_changed"] for r in sub)
        summary[name]["range_unchanged_with_file_fallback"]=summary[name]["file_unchanged_all_attempts"]+summary[name]["range_reuse"]-summary[name]["file_reuse"]
    dump(ROOT/"scored.json.gz",results)
    dump(ROOT/"results.json",dict(groups=summary,ineligible_reason=reasons,protocol=sha(ROOT/"PROTOCOL_RU.md"),forecasts=sha(ROOT/"scored.json.gz")))
    print(summary)

if __name__ == "__main__":
    run()

