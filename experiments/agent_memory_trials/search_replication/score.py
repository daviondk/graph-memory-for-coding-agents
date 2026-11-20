"""Execute every valid model decision against its fixed fixture and score the result."""
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import time

from build_study import ARMS, ROOT, dump, run_rg


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_choice(text):
    try:
        obj = json.loads(text.strip())
    except (ValueError, AttributeError):
        return None
    if isinstance(obj, dict) and set(obj) == {"choice"} and obj["choice"] in ["A", "B", "C", "D"]:
        return obj["choice"]
    return None


def pair_table(rows, x, y, measure):
    a = {r["case"]: r[measure] for r in rows if r["arm"] == x and r[measure] is not None}
    b = {r["case"]: r[measure] for r in rows if r["arm"] == y and r[measure] is not None}
    common = sorted(a.keys() & b.keys())
    wins = sum(a[k] > b[k] for k in common)
    losses = sum(a[k] < b[k] for k in common)
    d = wins + losses
    exact = min(1, 2 * sum(math.comb(d, i) for i in range(min(wins, losses) + 1)) / 2**d) if d else 1
    return dict(arm_a=x, arm_b=y, measure=measure, paired_cases=len(common), a_only=wins, b_only=losses,
                both_pass=sum(bool(a[k]) and bool(b[k]) for k in common),
                both_fail=sum(not a[k] and not b[k] for k in common),
                mean_paired_difference=(wins-losses) / len(common) if common else None, exact_two_sided_p=exact)


def main():
    for row in read(ROOT / "freeze.json")["files"]:
        path = ROOT / row["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"], f"Frozen input mismatch: {path}"
    cases = {c["id"]: c for c in read(ROOT / "cases.json")}
    rows = []
    executed = []
    for cell in read(ROOT / "allocation.json"):
        c = cases[cell["case"]]
        report = read(ROOT / "runs" / (cell["id"] + ".json"))
        choice = parse_choice(report["text"]) if report["status"] == "ok" else None
        evaluable = report["status"] != "infrastructure_error"
        rc, lines, duration = None, [], None
        argv = c["options"].get(choice)
        if argv:
            start = time.perf_counter()
            rc, lines = run_rg(ROOT / "fixtures" / c["id"], ".", argv)
            duration = round(time.perf_counter() - start, 6)
        expected = f"{c['target_path']}:{c['target_line']}:"
        found = any(line.replace("\\", "/").removeprefix("./").startswith(expected) for line in lines)
        open_shard = bool(argv and argv[-1] in c["unresolved_shards"])
        attempts = report["attempts"]
        tok = lambda field: sum((a.get("usage") or {}).get(field, 0) for a in attempts)
        row = {**cell, "mechanism": c["mechanism"], "ambiguous": c["ambiguous"], "symbol": c["symbol"],
               "target": c["target_path"], "target_line": c["target_line"], "model_status": report["status"],
               "model": report["model"], "choice": choice, "oracle_choice": c["oracle_choice"],
               "valid_choice": int(choice is not None), "chosen_shard": argv[-1] if argv else None,
               "pass": int(found) if evaluable else None, "previously_unresolved": int(open_shard) if evaluable else None,
               "exit_code": rc, "n_lines": len(lines), "exec_seconds": duration, "attempts": len(attempts),
               "input_tokens": tok("input_tokens"), "cached_input_tokens": tok("cached_input_tokens"),
               "output_tokens": tok("output_tokens"), "model_seconds": round(sum(a["elapsed_s"] for a in attempts), 3)}
        rows.append(row)
        executed.append(dict(id=cell["id"], case=cell["case"], choice=choice, executed_argv=argv, exit_code=rc, stdout=lines))
    dump(ROOT / "executed_actions.json", executed)
    with (ROOT / "observations.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    out = {}
    for arm in ARMS:
        a = [r for r in rows if r["arm"] == arm]
        ev = [r for r in a if r["pass"] is not None]
        out[arm] = dict(cases=len(a), evaluated=len(ev), pass_count=sum(r["pass"] for r in ev),
                        unresolved_choice_count=sum(r["previously_unresolved"] for r in ev),
                        unique_pass=sum(r["pass"] for r in ev if not r["ambiguous"]),
                        ambiguous_pass=sum(r["pass"] for r in ev if r["ambiguous"]),
                        valid_choices=sum(r["valid_choice"] for r in a),
                        failure_cases=[r["case"] for r in ev if not r["pass"]],
                        median_memory_chars=statistics.median(r["memory_chars"] for r in a),
                        median_model_seconds=statistics.median(r["model_seconds"] for r in a),
                        **{k: sum(r[k] for r in a) for k in ["input_tokens", "cached_input_tokens", "output_tokens", "attempts"]})
    contrasts = [pair_table(rows, x, y, measure) for x, y in [("structured","raw"), ("raw","summary"), ("structured","summary")]
                 for measure in ["pass", "previously_unresolved"]]
    dump(ROOT / "results.json", dict(arms=out, paired_contrasts=contrasts))


if __name__ == "__main__":
    main()
