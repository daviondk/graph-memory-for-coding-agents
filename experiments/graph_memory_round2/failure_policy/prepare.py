"""Fetch only the pinned aggregate JSON. Write deidentified features and outcomes separately."""
from pathlib import Path
import hashlib
import json
import urllib.request
from collections import Counter

ROOT = Path(__file__).resolve().parent
REV = "1827cdb9f8a939d653baf6be3d94f1e00589fe93"
BASE = f"https://raw.githubusercontent.com/Weypher/agent-failure-memory/{REV}/data/results/full/"
ARMS = ["HISTORY", "NONE", "SIGNAL", "REFLECT", "BOTH"]


def digest(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def write(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bucket(value, thresholds):
    if value is None:
        return "missing"
    assert type(value) is int and value >= 0
    return str(sum(value > threshold for threshold in thresholds))


def prepare():
    with urllib.request.urlopen(BASE + "C.json", timeout=60) as handle:
        blob = handle.read()
    data = json.loads(blob)
    first = {(a["task"], a["rep"]): a for a in data["first_attempts"]}
    assert len(first) == len(data["first_attempts"])
    features, labels, missing = [], {}, []
    observed_by_arm = {a: Counter() for a in ARMS}
    for record in data["instances"]:
        task, rep = record["task"], record["rep"]
        project, number = task.rsplit("/", 1)
        assert number.isdigit()
        r = first[task, rep]
        assert not r["resolved"] and r["status"] == record["a1_status"] and r["subtype"] == record["a1_subtype"]
        eid = digest(f"event:{task}|{rep}")
        assert eid not in labels
        armresults = {}
        for arm in ARMS:
            result = record["arms"].get(arm, {})
            outcome = result.get("outcome")
            assert outcome in {None, "resolved", "unresolved", "excluded_integrity", "harness"}
            observed_by_arm[arm][str(outcome)] += 1
            if outcome not in {"harness", None}:
                armresults[arm] = int(outcome == "resolved")
        if len(armresults) != len(ARMS):
            missing.append({"id": eid, "unavailable": [a for a in ARMS if a not in armresults]})
            continue
        labels[eid] = armresults
        x = {"status": r["status"], "subtype": r["subtype"], "responses": bucket(r.get("responses"), [3, 6])}
        for side, prefix in [("baseline_attempt", "changed"), ("baseline_traceback", "trace")]:
            for key in ["files", "functions"]:
                x[prefix + "_" + key] = bucket(record[side].get("n_suspected_" + key), [0, 1])
        x["changed_trace_files"] = x["changed_files"] + "/" + x["trace_files"]
        features.append({"id": eid, "task": digest("task:" + task), "project": digest("repo:" + project), "x": x})
    write("features.json", sorted(features, key=lambda r: r["id"]))
    write("labels.json", labels)
    write("collection.json", {"source": BASE + "C.json", "original_sha256": hashlib.sha256(blob).hexdigest(),
                             "first_attempts": len(first), "retry_episodes": len(data["instances"]),
                             "observations_per_arm_full_cohort": observed_by_arm, "missing": missing,
                             "complete_cases": len(features), "projects": len({r["project"] for r in features}),
                             "tasks": len({r["task"] for r in features}),
                             "feature_frequencies": {k: Counter(r["x"][k] for r in features) for k in features[0]["x"]}})
    print(f"{len(first)} initial, {len(data['instances'])} eligible, {len(features)} complete")


if __name__ == "__main__":
    prepare()
