"""Predict hidden members after revealing two paths. All selectors share one evidence payload."""
from collections import Counter
from heapq import nlargest
from itertools import combinations
from math import comb
from pathlib import Path
import random
from statistics import fmean
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "anchor_risk"))
from risk import History
from evaluate_risk import output, read
from joint import METHODS, score


def replay(stream, sparse):
    state = History()
    revs = []
    results = []
    for t, (sha, names) in enumerate(stream):
        paths = names if len(names) <= 64 else []
        if t >= len(stream) // 2 and len(paths) >= 3 and (not sparse or int(sha, 16) % 11 == 0):
            pair = list(combinations(paths, 2))[int(sha, 16) % comb(len(paths), 2)]
            a, b = (state.ids.get(p, -1) for p in pair)
            first, second = (state.select(x)["fill6"] for x in (a, b))
            selected = sorted(set(first).union(second))
            fallback = nlargest(10, range(len(state.ids)), key=lambda i: (state.frequency[i], -i))
            top, joint, members = score(selected, state.events, a, b, state.frequency, fallback)
            target = {state.ids.get(p, -2) for p in paths if p not in pair}
            hits = {m: len(set(top[m]).intersection(target)) for m in METHODS}
            results.append(dict(sha=sha, t=t, seeds=list(pair), denom=len(paths)-2, ranks=top, hits=hits,
                                evidence=[revs[j] for j in selected], joint=[revs[j] for j in joint],
                                members=members, overlap=len(first)+len(second)-len(selected)))
        if len(paths) >= 2:
            revs.append(sha)
        state.observe(paths)
    return results


def summarize(rows):
    if not rows:
        return {"n": 0}
    metrics = {}
    for m in METHODS:
        diff = [r["hits"][m] - r["hits"]["sum"] for r in rows]
        metrics[m] = dict(recall=fmean(r["hits"][m]/r["denom"] for r in rows),
                          hit=sum(r["hits"][m] > 0 for r in rows), wins=sum(x>0 for x in diff),
                          losses=sum(x<0 for x in diff), ties=diff.count(0),
                          changed=sum(r["ranks"][m] != r["ranks"]["sum"] for r in rows))
    return dict(n=len(rows), metrics=metrics, active=sum(bool(r["joint"]) for r in rows),
                events=sum(len(r["evidence"]) for r in rows), members=sum(r["members"] for r in rows),
                overlapping_reads_avoided=sum(r["overlap"] for r in rows))


def compare(entries, a, b):
    diffs = [100*(r["metrics"][a]["recall"]-r["metrics"][b]["recall"]) for r in entries if r["n"]]
    rng = random.Random(57201)
    draws = sorted(fmean(rng.choices(diffs, k=len(diffs))) for _ in range(20000))
    return dict(macro_pp=fmean(diffs), interval_pp=[draws[499],draws[19499]],
                projects=len(diffs), by_project_pp=diffs)


def main():
    inputs = {"replication": HERE.parent / "replication" / "events.json.gz",
              "long": HERE.parents[1] / "graph_memory_round56/event_intersection/long-events.json.gz",
              "new": HERE / "events.json.gz"}
    verify = "--verify" in sys.argv
    out = {}
    for label, path in inputs.items():
        projects = read(path)
        if label == "new":
            assert len(projects) == 6, "collection incomplete"
        groups = {repo: replay(stream, label == "long") for repo, stream in projects.items()}
        rows = [row for rs in groups.values() for row in rs]
        summaries = {project: summarize(rs) for project, rs in groups.items()}
        cases = list(summaries.values())
        out[label] = dict(projects=summaries, pooled=summarize(rows),
                          active=summarize([r for r in rows if r["joint"]]),
                          contrasts={m:compare(cases,"joint",m) for m in ("sum","placebo","harmonic","geometric")})
        output(HERE / f"{label}-queries.json.gz", groups, verify)
        print(label, len(rows), out[label]["contrasts"]["sum"], flush=True)
    output(HERE / "metrics.json", out, verify)


if __name__ == "__main__":
    main()
