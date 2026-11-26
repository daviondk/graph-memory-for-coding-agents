"""Independent exact-cost knapsack and arithmetic audit. Runs with the standard library."""
from collections import Counter, defaultdict
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import sys


D = Path(__file__).resolve().parent
R38 = D.parents[1] / "graph_memory_round38" / "edit_ready"
NAT = D.parent / "natural_invalidations"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def signed(path):
    assert digest(path) == load(path.parent / "manifest.json")["files"][path.name]
    return load(path)


@lru_cache(maxsize=4096)
def optimal(pool):
    """Optimize exact spends; tie-break on the smallest mask, excluding later blocks first."""
    total = 0
    head = []
    for idx, cost, score in pool:
        if total + cost > 1024:
            break
        total += cost
        head.append(idx)
    capacity = 2048 - total
    tail = pool[len(head):]
    best = {0: (0, 0)}
    for j, (idx, cost, score) in enumerate(tail):
        if cost > capacity:
            continue
        for spent, (value, negative_mask) in tuple(best.items()):
            new_cost = spent + cost
            if new_cost <= capacity:
                option = (value + score, negative_mask - (1 << j))
                if new_cost not in best or option > best[new_cost]:
                    best[new_cost] = option
    mask = -max(best.values())[1]
    return head + [idx for j, (idx, _, _) in enumerate(tail) if mask & (1 << j)]


def main():
    if "--seal" not in sys.argv:
        manifest = load(D / "manifest.json")["files"]
        assert set(manifest) == {p.name for p in D.iterdir() if p.is_file() and p.name != "manifest.json"}
        for name, expected in manifest.items():
            assert digest(D / name) == expected
    plans = load(D / "guarded-plans.json.gz")
    selections = load(D / "selections.json.gz")
    witnesses = {(run, at): counts for run, at, counts in load(D / "checked-text.json.gz")}
    original = signed(NAT / "plans.json.gz")
    schedule = signed(R38 / "schedule.json.gz")
    geometry = signed(D.parent / "span_updates" / "scored.json.gz")
    assert len(witnesses) == len(selections) == len(geometry) == 2696
    assert {(r["rid"], r["event"]) for r in geometry} == set(witnesses)
    ps, ss, ts = (load(D / name) for name in ["plan-seal.json", "selection-seal.json", "text-check.json"])
    assert digest(D / "PROTOCOL_RU.md") == ps["registered"]
    assert digest(D / "guarded-plans.json.gz") == ps["plans"]
    assert digest(D / "selections.json.gz") == ss["selection"]
    assert digest(D / "plan-seal.json") == ss["plans"]
    assert digest(D / "selection-seal.json") == ts["sealed"]
    assert digest(D / "checked-text.json.gz") == ts["evidence"]
    assert ts["raw_manifest"] == signed(R38 / "input-seal.json")["source_manifest"]
    assert digest(D / "plan.py") == ps["implementation"]
    assert digest(D / "select_updates.py") == ss["code"]
    assert digest(NAT / "score.py") == ss["solver"]
    geometry_audit = load(D / "geometry-check.json")
    assert geometry_audit["counts"] == {"geometry_exact": 2696, "receipts": 2696}
    assert not geometry_audit["differences"] and geometry_audit["selection"] == ts["sealed"]
    issues = defaultdict(lambda: [None, 0, 0, 0])
    unsafe = Counter()
    other_events, other_views = set(), set()
    total = Counter()
    for r in selections:
        run, at, path = r["run"], r["at"], r["path"]
        low, high = r["start"], r["end"]
        inc, rem = plans[run][str(at)]
        old = original[run][str(at)]
        assert sorted([b[0] for b in inc] + [b[0] for b in rem]) == list(range(len(old)))
        pool = [(i, size, value) for i, _, _, _, size, value, _ in inc]
        overlaps = {i for i, p, a, b, *_ in inc if p == path and max(low, a) <= min(high, b)}
        target = {i for i, p, *_ in inc if p == path}
        for name, deleted in [("old", set()), ("interval", overlaps), ("file", target)]:
            assert optimal(tuple(item for item in pool if item[0] not in deleted)) == r[name]
            total["optimal_lists"] += 1
        assert int(r["old"] == r["interval"]) == r["same"]
        assert int(r["old"] == r["file"]) == r["file_same"]
        obs = witnesses[run, at]
        assert all(obs.get(label + "_wrong_lines", 0) == obs.get(label + "_wrong_bytes", 0) == 0
                   for label in ["retained", "selected_before", "survivors_after", "selected_after", "fully_reused_selected_after"])
        assert sum(old[i][3] for i in target) == obs["retained_bytes"]
        assert sum(old[i][3] for i in target - overlaps) == obs.get("survivors_after_bytes", 0)
        assert sum(old[i][3] for i in target.intersection(r["interval"])) == obs.get("selected_after_bytes", 0)
        removed = {row[0] for row in rem}
        assert sum(old[i][3] for i in removed) == r["cost"]["removed_bytes"]
        assert sum(old[i][2] - old[i][1] + 1 for i in removed) == r["cost"]["removed_rows"]
        for idx, reason, view in rem:
            other_path = old[idx][0]
            if other_path == path:
                continue
            assert reason == "gate"
            events = schedule[run]["events"]
            def boundary(e):
                return e[1] == "reset" or (e[1] != "view" and e[2] == other_path)
            before = next((e[1] for e in reversed(events) if e[0] < at and boundary(e)), "end")
            after = next((e[1] for e in events if e[0] > at and boundary(e)), "end")
            unsafe[(before, after)] += 1
            other_events.add((run, at))
            other_views.add((run, view))
        issue = issues[r["issue"]]
        assert issue[0] is None or issue[0] == r["held"]
        issue[0] = r["held"]
        issue[1] += 1
        issue[2] += r["same"]
        issue[3] += r["file_same"]
    assert unsafe == {("reset", "reset"): 302}
    stats = load(D / "results.json")
    assert dict(issues) == stats["issue_counts"]
    for label, filt in [("holdout", lambda v: v[0]), ("all", lambda v: True)]:
        vals = [(a - b) / n for h, n, a, b in issues.values() if filt([h])]
        assert abs(100 * sum(vals) / len(vals) - stats["strata"][label]["range_minus_file_issue_macro_pp"]) < 1e-9
    outcome = dict(optimal_lists=total["optimal_lists"], edited_receipts=len(witnesses),
                   outside_target_rejected_blocks=302, outside_target_distinct_views=len(other_views),
                   outside_target_events=len(other_events), outside_target_boundary_both_sides_reset=302)
    if "--seal" in sys.argv:
        (D / "replication.json").write_bytes((json.dumps(outcome, sort_keys=True, indent=2) + "\n").encode())
    else:
        assert load(D / "replication.json") == outcome
    print(outcome)


if __name__ == "__main__":
    main()
