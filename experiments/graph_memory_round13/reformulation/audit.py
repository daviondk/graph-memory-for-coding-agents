"""Reopen originals, verify witness chronology and changed names, and time ranking without disk I/O."""
import collections
import concurrent.futures
import json
import platform
import random
import statistics
import subprocess
import time
from pathlib import Path

import grade
import prefix
import pr_oracle
import rank

ROOT = Path(__file__).resolve().parent

def git_paths(pr):
    mirror = pr_oracle.CACHE / (pr["repo"].replace("/", "__") + ".git")
    command = ["git", "-C", str(mirror), "diff-tree", "--no-commit-id", "--name-only",
               "-r", "-z", "--no-renames", "--diff-filter=MDT", pr["base"], pr["merge"]]
    paths = subprocess.check_output(command).decode("utf-8", "surrogateescape").split("\0")
    assert sorted(p for p in paths if p.endswith(".py")) == pr["existing_py"]
    assert pr["old_time"] <= pr["new_time"] and pr["parent"] == pr["base"]
    return 1

def q(vals):
    return {"median": statistics.median(vals), "p90": grade.quantile(vals, .9)}

def main(panel):
    rank.D = panel
    roster = {r["iid"]: r for r in rank.load("roster.json")}
    inputs = rank.load("inputs.json.gz")
    forecasts = {r["id"]: r["rank"] for r in rank.load("frozen_rankings.json.gz")}
    labs = {r["id"]: r for r in rank.load("navigation_labels.json.gz")}
    pr = rank.load("patch_labels.json.gz")
    group = collections.defaultdict(list)
    for row in inputs:
        group[row["iid"]].append(row)
    check = collections.Counter()
    for iid, rows in group.items():
        task = roster[iid]
        data = (prefix.V / "benchmark" / task["file"]).read_bytes()
        assert prefix.h(data) == task["sha"]
        msgs = json.loads(data)["messages"]
        steps = list(prefix.calls(msgs))
        visible = {}
        for row in rows:
            i = row["index"]
            ai, mi, cid, cmd, tool = steps[i]
            assert ai == i and cid == row["id"].split("|", 1)[1] and mi == row["message"]
            assert prefix.shown(tool) == (1, "")
            assert tool["extra"]["raw_output"].strip() == ""
            check["anchors"] += 1
            for path, memory in row["docs"].items():
                for key in ("last", "direct", "read"):
                    assert memory[key] < i
                if not memory["evidence"]:
                    assert path == row["key"]["scope"] and memory["support"] == 0 and not memory["snip"]
                    check["explicit_unseen_scope_slots"] += 1
                for j, ref, kind, digest in memory["evidence"]:
                    assert 0 <= j < i
                    _, _, original, command, result = steps[j]
                    assert ref == original
                    if j not in visible:
                        rc, out = prefix.shown(result)
                        assert rc == 0
                        visible[j] = {(root, p, k): prefix.h(prefix.excerpt(lines).encode())[:16]
                                      for root, p, k, lines in prefix.inspect(command, out, task["repo"])}
                    assert visible[j][(row["key"]["root"], path, kind)] == digest
                    check["retained_witnesses"] += 1
            if labs[row["id"]]["target"]:
                event = labs[row["id"]]["target"]
                assert 1 <= event["delta"] <= 5
                ff = steps[i + event["delta"]]
                assert event["call"] == ff[2] and event["command"] == ff[3]
                rc, out = prefix.shown(ff[4])
                assert rc == 0 and prefix.h(out.encode()) == event["visible_sha"]
                check["future_view_hashes"] += 1
        check["original_task_hashes"] += 1
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        check["independent_git_difftrees"] = sum(pool.map(git_paths, [x for x in pr if x.get("strict")]))
    rng = random.Random(17438)
    timings = []
    for rep in range(3):
        order = inputs[:]
        rng.shuffle(order)
        for r in order:
            start = time.perf_counter_ns()
            ranked, cost = rank.calculate(r)
            total = time.perf_counter_ns() - start
            assert ranked == forecasts[r["id"]]
            timings.append({"repeat": rep, "id": r["id"], "all_ns": total, **cost})
    rank.dump("timing_rows.json.gz", timings)
    rank.dump("verification.json", {"counts": check, "replayed_rankings": len(timings),
              "python": platform.python_version(), "os": platform.platform(),
              "cpu_ms_per_anchor": {k: q([x[k] / 1e6 for x in timings])
                                    for k in ("all_ns", "prepare_ns", "graph_ns", "shuffled_ns")},
              "timing_scope": "elapsed wall clock, one thread, no disk; includes real and shuffled graphs",
              "audit_scope": "all anchors, all retained entry witness hashes, all label-bearing next views, all strict diff-tree pairs"})
    print(panel.name, check, flush=True)

if __name__ == "__main__":
    for p in (ROOT, ROOT / "replication"):
        main(p)
