"""Verify all source coordinates and native metrics through independent set arithmetic."""
import collections
import random
from pathlib import Path
from statistics import mean

from predict import ROOT, WORK, load, digest, write

REFERENCE = WORK / "graph_memory_round16/anchor_transfer"
BENCHMARK = Path("D:/CodexResearch/x20-round15-external-scoring/swe-explore.jsonl")


def points(regions):
    return {(p, n) for p, left, right in regions for n in range(left, right+1)}


def main():
    import json
    locks = load(ROOT/"prediction-lock.json")
    for name, h in locks["inputs"].items():
        assert digest(WORK/name) == h
    for name, h in locks["files"].items():
        assert digest(ROOT/name) == h
    gold = {}
    for l in BENCHMARK.read_bytes().splitlines():
        row = json.loads(l)
        gold[row["instance_id"]] = row["ground_truth"]["read_core_regions"]
    records = load(ROOT/"scored.json.gz")
    check_count = 0
    diffs = collections.defaultdict(list)
    by_repo = collections.defaultdict(list)
    cases = []
    for row in records:
        iid = row["instance_id"]
        core = points((r["path"],r["start"],r["end"]) for r in gold[iid])
        for arm, regions in row["regions"].items():
            chosen = points(regions)
            assert len(chosen) == min(row["lines_seen"],60)
            matched = len(chosen & core)
            pr = matched / len(chosen) if chosen else 0
            rec = matched / len(core) if core else 0
            f1 = 2*pr*rec/(pr+rec) if (pr+rec) else 0
            for met,val in [("precision",pr),("recall",rec),("f1_score",f1)]:
                assert abs(row["scores"][arm][met] - val)<1e-11, (iid,arm,met)
                check_count += 1
        if row["panel"] != "independent":
            continue
        delta = row["scores"]["scope24"]["precision"]-row["scores"]["lexical24"]["precision"]
        by_repo[iid.rsplit("-",1)[0]].append(delta)
        diffs[iid].append(delta)
        if abs(delta)>1e-10:
            cases.append(dict(id=iid, source=row["source"], delta=delta))
    assert all(len(v)==2 for v in diffs.values())
    rng = random.Random(1731)
    values = list(by_repo.values())
    samples=sorted(mean(d for group in rng.choices(values,k=len(values)) for d in group) for _ in range(5000))
    omit={k:mean(d for kk, v in by_repo.items() if kk!=k for d in v) for k in by_repo}
    details=dict(independent_native_values=check_count, patch_rows_verified_separately=True, projects=len(values),
                 primary_by_repository={k:{"episodes":len(v),"delta":mean(v)} for k,v in by_repo.items()},
                 primary_repository_bootstrap=[samples[124],samples[4874]],
                 primary_leave_one_repository_out=omit,episodes_with_metric_change=cases)
    write("verification.json",details)
    print(check_count,details["primary_repository_bootstrap"],[min(omit.values()),max(omit.values())])


if __name__ == "__main__":
    main()

