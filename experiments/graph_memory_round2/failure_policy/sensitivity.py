"""Exploratory full-suite sensitivity of the frozen policies and an unweighted constant."""
import hashlib
import json
import urllib.request
from pathlib import Path
from collections import Counter
import numpy as np
from prepare import BASE, ARMS, digest, write

ROOT = Path(__file__).resolve().parent


def main():
    rows = json.loads((ROOT/"features.json").read_text(encoding="utf-8"))
    ys = json.loads((ROOT/"labels.json").read_text(encoding="utf-8"))
    pred = json.loads((ROOT/"predictions.json").read_text(encoding="utf-8"))
    with urllib.request.urlopen(BASE + "fullsuite-r1.json",timeout=60) as h:
        blob = h.read()
    raw = json.loads(blob)
    lookup = {}
    for item in raw["rows"]:
        eid = digest(f"event:{item['task']}|{item['rep']}")
        if item["kind"] != "retry" or eid not in ys:
            continue
        arm = item["arm"]
        assert ys[eid][arm] == 1 and (eid,arm) not in lookup
        lookup[eid,arm] = {"clean": item["suite_clean"], "mode": item["mode"]}
    y2 = {}
    modes = Counter()
    for row in rows:
        eid = row["id"]
        status = {}
        for a,v in ys[eid].items():
            if v == 0:
                status[a] = 0
            else:
                fs = lookup[eid,a]
                if fs["clean"] is not None:
                    status[a] = int(fs["clean"])
                    modes[fs["mode"]] += 1
        if len(status) == len(ARMS):
            y2[eid] = status
    micro = {}
    for row in rows:
        train = [ys[r["id"]] for r in rows if r["project"] != row["project"]]
        totals = [sum(ep[a] for ep in train) for a in ARMS]
        micro[row["id"]] = ARMS[totals.index(max(totals))]
    policies = list(next(iter(pred.values()))) + ARMS + ["constant_cv_row_weight"]
    strict = {}
    for key in policies:
        hits, base = [], []
        for r in rows:
            eid = r["id"]
            a = key if key in ARMS else (micro[eid] if key == "constant_cv_row_weight" else pred[eid][key])
            base.append(ys[eid][a])
            if eid in y2:
                hits.append(y2[eid][a])
        strict[key] = {"trigger_full_n": len(base),"trigger_full_k":sum(base),"strict_n":len(hits),"strict_k":sum(hits)}
    out = {"url":BASE+"fullsuite-r1.json", "sha256":hashlib.sha256(blob).hexdigest(),
           "rule":raw["rule"], "n_original_complete":len(rows),"n_fully_checkable":len(y2),
           "n_positive_unknown":sum(v["clean"] is None for v in lookup.values()),
           "all_observed_positive_verification_modes":modes, "all_results":strict,
           "complete_checkable_ids":sorted(y2)}
    write("sensitivity.json",out)
    print("strict complete",len(y2),"positive unmeasured",out["n_positive_unknown"],"details",strict)


if __name__ == "__main__":
    main()
