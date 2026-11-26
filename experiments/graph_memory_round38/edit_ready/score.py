"""Evaluate the sealed public predictions. This program never imports the predictor."""
from collections import Counter, defaultdict
from random import Random
from statistics import mean
from common import D, get, save, sha


FIELDS = ["certified_lines", "cache_lines", "cache_bytes", "absent", "different_text", "unwitnessed_lf"]


def compare(refs, facts, path, target):
    facts_here = [facts[i] for i in refs]
    addressed = {(p, n): (digest, witness) for p, n, digest, _, witness in facts_here}
    assert len(addressed) == len(facts_here)
    reasons = Counter()
    for n, expected, need_lf in target:
        fact = addressed.get((path, n))
        if fact is None:
            reasons["absent"] += 1
        elif fact[0] != expected:
            reasons["different_text"] += 1
        elif need_lf and not fact[1]:
            reasons["unwitnessed_lf"] += 1
        else:
            reasons["certified"] += 1
    return [reasons["certified"], len(refs), sum(13 + x[3] for x in facts_here),
            reasons["absent"], reasons["different_text"], reasons["unwitnessed_lf"]]


def evaluate(pred, schedule, views, targets):
    output, reasons = [], Counter()
    for rid, meta in schedule.items():
        facts, admitted = [], 0
        assert set(pred["snapshots"][rid]) == set(targets[rid])
        for event in meta["events"]:
            at, kind = event[:2]
            if kind == "view":
                facts.extend((event[2], *row) for row in views[rid][str(at)])
            if kind != "snapshot+invalidate":
                continue
            target = targets[rid][str(at)]
            reasons[(meta["group"], target["reason"])] += 1
            if target["reason"] != "ok":
                continue
            assert target["path"] == event[2] and target["atoms"]
            part = meta["group"] + ("_later" if admitted else "_first")
            admitted += 1
            scores = [compare(refs, facts, event[2], target["atoms"]) for refs in pred["snapshots"][rid][str(at)]]
            output.append(dict(run=rid, at=at, issue=meta["issue"], repo=meta["repo"], part=part,
                               path=event[2], lines=len(target["atoms"]), old_bytes=target["old_bytes"],
                               partial_start=target["partial_start"], partial_end=target["partial_end"],
                               leading_or_trailing_eol=target["leading_or_trailing_eol"], scores=scores))
    return output, {f"{group}:{reason}": n for (group, reason), n in reasons.items()}


def quantile(a, q):
    pos = (len(a) - 1) * q
    j = int(pos)
    return a[j] + (a[min(j + 1, len(a) - 1)] - a[j]) * (pos - j)


def summarize(rows, methods, interval):
    by_issue = defaultdict(list)
    for row in rows:
        by_issue[row["issue"]].append(row)
    results = {}
    for col, method in enumerate(methods):
        complete = lambda r: int(r["scores"][col][0] == r["lines"])
        results[method] = dict(complete=sum(map(complete, rows)),
            issue_macro_complete=mean(mean(map(complete, rs)) for rs in by_issue.values()),
            mean_certified_fraction=mean(r["scores"][col][0] / r["lines"] for r in rows),
            mean_cache_lines=mean(r["scores"][col][1] for r in rows),
            mean_cache_bytes=mean(r["scores"][col][2] for r in rows),
            loss_counts={name: sum(r["scores"][col][i] for r in rows) for i, name in enumerate(FIELDS) if i >= 3})
    c1, c0 = methods.index("focus-64"), methods.index("tail-64")
    def diff(r):
        return int(r["scores"][c1][0] == r["lines"]) - int(r["scores"][c0][0] == r["lines"])
    deltas = [mean(map(diff, by_issue[i])) for i in sorted(by_issue)]
    contrast = dict(issue_macro_pp=100*mean(deltas), focus_only=sum(diff(r) == 1 for r in rows),
                    tail_only=sum(diff(r) == -1 for r in rows))
    if interval:
        rng = Random(380671)
        draws = sorted(100 * sum(rng.choices(deltas, k=len(deltas))) / len(deltas) for _ in range(10000))
        contrast["ci95_pp"] = [quantile(draws, q) for q in (0.025, 0.975)]
    return dict(operations=len(rows), issues=len(by_issue), runs=len({r["run"] for r in rows}),
                repos=len({r["repo"] for r in rows}), affected_lines=sum(r["lines"] for r in rows),
                methods=results, contrast=contrast)


def main():
    seal, inputs = [get(D / n) for n in ("prediction-seal.json", "input-seal.json")]
    assert sha(D/"input-seal.json") == seal["inputs"] and sha(D/"predictions.json.gz") == seal["predictions"]
    assert all(sha(D/n) == checksum for n, checksum in inputs["artifacts"].items())
    assert all(sha(D/n) == seal[key] for n, key in [("predict.py", "implementation"),
        ("common.py", "common"), ("IMPLEMENTATION_RU.md", "implementation_notes"), ("PROTOCOL_RU.md", "protocol")])
    pred, schedule, views, targets = [get(D / n) for n in ("predictions.json.gz", "schedule.json.gz", "visible.json.gz", "sealed-targets.json.gz")]
    assert pred["methods"] == seal["methods"] and set(pred["snapshots"]) == set(targets) == set(schedule)
    rows, reasons = evaluate(pred, schedule, views, targets)
    scored = save(D/"scored.json.gz", dict(methods=pred["methods"], fields=FIELDS, records=rows))
    subgroups = {p: summarize([r for r in rows if r["part"] == p], pred["methods"], p == "main_first")
                 for p in sorted({r["part"] for r in rows})}
    save(D/"results.json", dict(prediction_seal=sha(D/"prediction-seal.json"), scored=scored,
                                reasons=reasons, total=len(rows), strata=subgroups))
    print({p: (s["operations"], s["issues"], s["contrast"]) for p, s in subgroups.items()})


if __name__ == "__main__":
    main()
