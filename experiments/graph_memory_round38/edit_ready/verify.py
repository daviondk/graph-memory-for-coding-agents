"""Independent verifier. Uses no projector, predictor or scorer routines."""
from collections import Counter, defaultdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
from random import Random
from statistics import fmean

D = Path(__file__).resolve().parent
R37 = D.parents[1] / "graph_memory_round37"


def digest(p):
    return sha256(p.read_bytes()).hexdigest()


def load(p):
    data = p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix == ".gz" else data)


def path_id(s):
    return sha256(s.encode()).hexdigest()


def verify_signed(schedule, views):
    ep = R37 / "code_visibility/events.json.gz"
    bp = R37 / "edit_demand/native_boundaries.json.gz"
    assert digest(ep) == "b4527e3337e2d567495d4836f440b56cb59605dec84dfff6cb0368c6924c7449"
    assert digest(bp) == "bd21269212e38ddd970acb7c4a528360bed10b0826c6f7081ef4000d2762bdae"
    original, native = load(ep), load(bp)
    audits = Counter()
    found = set()
    for rid, run in original.items():
        sequence = run["events"] + [[lo + .5, "barrier"] for lo, hi in native[rid]["gaps"]]
        sequence.sort()
        op_receipts = {start: (end, addr) for start, end, cmd, addr in native[rid]["successful_writes"] if cmd == "str_replace"}
        # Examine each potentially eligible run/action directly in both directions.
        checkpoints = {}
        kept = set()
        for ix, e in enumerate(sequence):
            at, kind = e[:2]
            if kind != "write_start" or at not in op_receipts:
                continue
            path = e[2]
            end, addr = op_receipts[at]
            assert addr == path_id(path)
            window_start = ix
            while window_start and sequence[window_start - 1][1] != "barrier":
                window_start -= 1
            prior = [v for v in sequence[window_start:ix] if len(v) > 2 and v[2] == path and (v[1] != "read" or v[4])]
            if not prior or prior[-1][1] != "read":
                continue
            overlapping = [v for v in sequence[ix + 1:] if v[0] < end and (v[1] == "barrier" or v[2] == path and v[1] != "read")]
            if overlapping:
                continue
            checkpoints[at] = addr
            kept.update(range(window_start, ix + 1))
        if not checkpoints:
            assert rid not in schedule
            continue
        found.add(rid)
        expected = []
        for ix, e in enumerate(sequence):
            at, kind = e[:2]
            if kind == "barrier":
                expected.append([at, "reset"])
            elif ix in kept:
                addr = path_id(e[2])
                if kind == "read":
                    if not e[4]:
                        continue
                    expected.append([at, "view", addr])
                    rows = views[rid][str(at)]
                    dictionary = {n: d for n, d, size, lf in rows}
                    assert len(rows) == len(dictionary) == e[4]
                    assert all(dictionary[n] == d for n, d in e[3])
                    assert all(lf == int(n + 1 in dictionary) for n, d, size, lf in rows)
                    audits["views_checked"] += 1
                    audits["signed_informative_row_observations"] += len(e[3])
                    audits["numbered_row_observations"] += len(rows)
                else:
                    expected.append([at, "snapshot+invalidate" if at in checkpoints else "invalidate", addr])
        assert expected == schedule[rid]["events"]
        assert set(views[rid]) == {str(e[0]) for e in expected if e[1] == "view"}
        assert run["issue"] == schedule[rid]["issue"] and run["repo"] == schedule[rid]["repo"]
        group = "main" if run["subset"] in ["predecessors", "main_takeovers"] else "additional"
        assert group == schedule[rid]["group"]
        audits["snapshots_checked"] += len(checkpoints)
    assert found == set(views) == set(schedule)
    return dict(audits)


def rank(current, last, policy):
    lo, hi = current[0][1], current[-1][1]
    if policy == "tail":
        return list(reversed(current))
    if policy in ("head", "full"):
        return current
    if policy == "grid":
        positions = {}
        def visit(a, b, node):
            if a > b:
                return
            mid = (a + b) // 2
            positions[mid] = node
            visit(a, mid - 1, 2*node)
            visit(mid + 1, b, 2*node + 1)
        visit(lo, hi, 1)
        return sorted(current, key=lambda f: positions[f[1]])
    if policy == "focus" and last and current[0][0] == last[0] and max(last[1], lo) <= min(last[2], hi):
        lo, hi = max(last[1], lo), min(last[2], hi)
    return sorted(current, key=lambda f: (abs(f[1] - (lo+hi)/2), f[1]))


def update(previous, observations, b):
    old = {f[:2]: f for f in previous}
    merged = []
    for row in observations:
        past = old.pop(row[:2], None)
        merged.append(past if past and past[2] == row[2] and past[4] > row[4] else row)
    merged.extend(old.values())
    if b == "all":
        return merged
    if b.isdecimal():
        return merged[:int(b)]
    chosen, used = [], 0
    for row in merged:
        if used + row[3] + 13 <= 2048:
            chosen.append(row)
            used += row[3] + 13
    return chosen


def verify_replay(schedule, visible, predictions, targets, scored):
    methods = predictions["methods"]
    assert methods == scored["methods"]
    index = {(r["run"], r["at"]): r for r in scored["records"]}
    checked = 0
    for run, meta in schedule.items():
        last, ref, accepted = None, 0, 0
        memory = [[] for _ in methods]
        for event in meta["events"]:
            at, kind = event[:2]
            if kind == "reset":
                last = None
                memory = [[] for _ in methods]
                continue
            path = event[2]
            if kind == "view":
                observations = [(path, *row, j + ref) for j, row in enumerate(visible[run][str(at)])]
                ref += len(observations)
                ranked = {}
                for j, name in enumerate(methods):
                    p, cap = name.split("-") if "-" in name else ("full", "all")
                    if p not in ranked:
                        ranked[p] = rank(observations, last, p)
                    memory[j] = update(memory[j], ranked[p], cap)
                last = (path, observations[0][1], observations[-1][1])
                continue
            if kind == "snapshot+invalidate":
                snap = predictions["snapshots"][run][str(at)]
                assert [[f[-1] for f in mem] for mem in memory] == snap
                t = targets[run][str(at)]
                if t["reason"] == "ok":
                    assert path == t["path"]
                    row = index.pop((run, at))
                    assert row["part"] == meta["group"] + ("_later" if accepted else "_first")
                    assert row["old_bytes"] == t["old_bytes"] and row["lines"] == len(t["atoms"])
                    assert row["issue"] == meta["issue"] and row["repo"] == meta["repo"]
                    accepted += 1
                    for j, mem in enumerate(memory):
                        local = {f[1]: (f[2], f[4]) for f in mem if f[0] == path}
                        addresses = sum(n in local for n, _, lf in t["atoms"])
                        identical = sum(n in local and local[n][0] == d for n, d, lf in t["atoms"])
                        covered = sum(n in local and local[n][0] == d and local[n][1] >= lf for n, d, lf in t["atoms"])
                        assert row["scores"][j] == [covered, len(mem), 13*len(mem) + sum(f[3] for f in mem),
                            len(t["atoms"]) - addresses, addresses - identical, identical - covered]
                        checked += 1
            memory = [[f for f in mem if f[0] != path] for mem in memory]
    assert not index
    return checked


def verify_metrics(scored, results):
    methods = scored["methods"]
    for part, summary in results["strata"].items():
        rows = [r for r in scored["records"] if r["part"] == part]
        issue_rates = {}
        for j, name in enumerate(methods):
            groups = defaultdict(list)
            for r in rows:
                groups[r["issue"]].append(r["scores"][j][0] == r["lines"])
            rates = {i: fmean(vals) for i, vals in groups.items()}
            issue_rates[name] = rates
            metrics = summary["methods"][name]
            assert metrics["complete"] == sum(sum(x) for x in groups.values())
            assert abs(metrics["issue_macro_complete"] - fmean(rates.values())) < 1e-12
            for key, col in (("mean_cache_lines", 1), ("mean_cache_bytes", 2)):
                assert abs(metrics[key] - fmean(r["scores"][j][col] for r in rows)) < 1e-10
            assert abs(metrics["mean_certified_fraction"] - fmean(r["scores"][j][0]/r["lines"] for r in rows)) < 1e-12
        deltas = [(issue_rates["focus-64"][i] - issue_rates["tail-64"][i])*100 for i in sorted(issue_rates["tail-64"])]
        assert abs(fmean(deltas) - summary["contrast"]["issue_macro_pp"]) < 1e-12
        if part == "main_first":
            gen = Random(380671)
            draws = sorted(fmean(deltas[int(gen.random()*len(deltas))] for z in deltas) for _ in range(10000))
            for q, reported in zip((.025, .975), summary["contrast"]["ci95_pp"]):
                x = 9999*q
                a, fraction = divmod(x, 1)
                assert abs(draws[int(a)]*(1-fraction) + draws[int(a)+1]*fraction - reported) < 1e-9


def main():
    s, v, p, t, outcomes, results = [load(D/n) for n in ("schedule.json.gz", "visible.json.gz",
        "predictions.json.gz", "sealed-targets.json.gz", "scored.json.gz", "results.json")]
    ins, seal = load(D/"input-seal.json"), load(D/"prediction-seal.json")
    assert all(digest(D/f) == expected for f, expected in ins["artifacts"].items())
    assert digest(D/"predictions.json.gz") == seal["predictions"] and digest(D/"scored.json.gz") == results["scored"]
    assert digest(D/"prediction-seal.json") == results["prediction_seal"]
    audit = verify_signed(s, v)
    audit["method_episode_checks"] = verify_replay(s, v, p, t, outcomes)
    verify_metrics(outcomes, results)
    audit["bootstrap_draws_verified"] = 10000
    audit["prediction_sha256"] = seal["predictions"]
    audit["score_sha256"] = results["scored"]
    (D/"independent.json").write_bytes((json.dumps(audit, sort_keys=True, indent=2) + "\n").encode())
    print(audit)


if __name__ == "__main__":
    main()
