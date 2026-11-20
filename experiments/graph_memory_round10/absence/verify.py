"""Independent uninstrumented replays and accounting on the locked R10 sample."""
import concurrent.futures
import json
import statistics
import subprocess
import sys
from pathlib import Path

from experiment import D, cases, digest, enc, environment, get, manifest, save, sealed, sha
from workloads import passed, run


def replay(item):
    project, state, case = item
    root = D / "states" / project / state
    output = subprocess.check_output(
        [sys.executable, "-B", str(D / "verify.py"), "child", project, case],
        env=environment(root), cwd=root, timeout=45,
    )
    actual = json.loads(output)
    relative = Path(project) / state / (case.replace("/", "_") + ".json")
    old, new = [get(D / phase / relative) for phase in ("past", "future")]
    for field in ("value", "pass_test", "positive", "negative", "directories"):
        assert old[field] == new[field], (relative, field)
    assert actual == {"value": old["value"], "contract": old["pass_test"]}, relative
    return {"project": project, "state": state, "case": case, "value_sha": sha(enc(actual["value"])), "contract": actual["contract"]}


def summarize(nums):
    return {"min": min(nums), "median": statistics.median(nums), "max": max(nums), "sum": sum(nums)}


def main():
    jobs = sealed()
    manifests = get(D / "manifest.json")
    state_count = 0
    operation_ids = []
    for project, states in manifests.items():
        for state, contents in states.items():
            assert manifest(D / "states" / project / state) == contents
            state_count += 1
            operation_ids.extend((project, state, case) for case in cases(project))
    artifacts = []
    for rec in get(D / "sources.lock.json"):
        artifacts.append(rec)
        if rec.get("sdist"):
            artifacts.append(rec["sdist"])
    for rec in artifacts:
        assert digest(D / "sources" / rec["file"]) == rec["sha256"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        replayed = list(pool.map(replay, operation_ids))
    save(D / "uninstrumented_replay.json", replayed)
    rows = get(D / "rows.json")
    assert len(rows) == 84 and len(jobs) == 22 and len(replayed) == 72
    lookup = {r["id"]: r for r in jobs}
    assert len({(r["id"], r["case"]) for r in rows}) == len(rows)
    unique = {(r["project"], r["old"], r["case"]):r for r in rows}
    assert set(unique) == set(operation_ids)
    # Independent aggregate of policy decisions and score keyed by the actual output value.
    result = get(D / "results.json")
    for panel in ("published","optional","placebo"):
        group = [r for r in rows if r["panel"] == panel]
        for method in ("negative_keys","directory","positive","testmon","keep","always"):
            chosen = [r for r in group if r["decision"][method]]
            missed = [r for r in group if r["changed_value"] and not r["decision"][method]]
            assert len(chosen) == result[panel+"_both"]["policies"][method]["rerun"]
            assert len(missed) == result[panel+"_both"]["policies"][method]["stale"]
    byte_stats = {}
    for panel in ("libraries","tzdata","all"):
        selected = [r for r in unique.values() if panel == "all" or (r["project"] == "tzdata") == (panel == "tzdata")]
        per = {}
        for metric in ("bytes","gzip_bytes"):
            methods = {k:summarize([r["memory"][k][metric] for r in selected]) for k in ("positive","directory","negative_keys","neg_only")}
            methods["marginal_exact_minus_positive"] = summarize([r["memory"]["negative_keys"][metric] - r["memory"]["positive"][metric] for r in selected])
            per[metric] = methods
        byte_stats[panel] = {"unique_prior_states_ops": len(selected), **per}
    false_positives = [{"id":r["id"], "case":r["case"], "positive":r["positive_hit"],"negative":r["negative_hit"]} for r in rows if not r["changed_value"] and r["decision"]["negative_keys"]]
    missed_testmon = [{"id":r["id"],"case":r["case"]} for r in rows if r["changed_value"] and not r["plugin"]]
    upstream = get(D / "upstream_execution" / "results.json")
    per_source = {str((x["project"],x["state"])): dict((k,list(x["units"].values()).count(k)) for k in sorted(set(x["units"].values()))) for x in upstream}
    assert sum(len(x["units"]) for x in upstream if x["state"] == "B" and set(x["units"].values()) == {"passed"}) == 37
    assert all(set(x["units"].values()) == {"skipped"} for x in upstream if x["state"] != "B")
    plugin = [get(D / "plugin" / p / "receipt.json") for p in lookup]
    db = {phase:summarize([rec[phase]["db_bytes"] for rec in plugin]) for phase in ("build","select")}
    cost = {"storage":byte_stats,"plugin_db_bytes_per_suite": db, "negative_keys_false_positives":false_positives,"testmon_stale":missed_testmon,"original_upstream_pytest":per_source}
    save(D / "accounting.json",cost)
    save(D / "verification.json", {"verified_archives":len(artifacts), "verified_state_trees":state_count,"scored_transitions":len(jobs),"scored_decisions":len(rows),"uninstrumented_replays":len(replayed),"score_table_sha":digest(D/"results.json"),"raw_rows_sha":digest(D/"rows.json"),"replay_sha":digest(D/"uninstrumented_replay.json"),"accounting_sha":digest(D/"accounting.json")})
    print(json.dumps({"verification":get(D/"verification.json"),"bytes":{p:b["bytes"]["marginal_exact_minus_positive"] for p,b in byte_stats.items()},"fp":[(x["id"],x["case"]) for x in false_positives],"db":db}))


if __name__ == "__main__":
    if sys.argv[1:] and sys.argv[1] == "child":
        root = Path.cwd().resolve()
        sys.path.insert(0,str(root/"vendor"))
        project, case = sys.argv[2:]
        value = run(project,case,root)
        print(json.dumps({"value":value,"contract":passed(project,case,value)}))
    else:
        main()
