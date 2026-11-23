"""Measure overlap with exactly removed/replaced preimage lines of the verified PR."""
import collections
import random
import re
from statistics import mean, median

from pyarrow import parquet
from unidiff import PatchSet

from predict import ROOT, NEW, ISSUES, digest, load, write


def unidiff_old(text):
    return {(file.source_file.removeprefix("a/"), line.source_line_no)
            for file in PatchSet(text.splitlines(keepends=True)) if file.source_file.endswith(".py")
            for hunk in file for line in hunk if line.is_removed}


def original_lines(text):
    keys = set()
    path = None
    remaining = added = 0
    for line in text.splitlines():
        if remaining or added:
            if line.startswith("-"):
                if path and path.endswith(".py"):
                    keys.add((path, old))
                old += 1
                remaining -= 1
            elif line.startswith("+"):
                added -= 1
            elif line.startswith(" "):
                old += 1
                remaining -= 1
                added -= 1
            else:
                assert line.startswith("\\ No newline"), line
            assert remaining >= 0 and added >= 0
        elif line.startswith("--- "):
            path = line[4:].split("\t",1)[0].removeprefix("a/")
        elif line.startswith("@@"):
            match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@", line)
            assert match
            old = int(match[1])
            remaining = int(match[2] or "1")
            added = int(match[3] or "1")
    assert remaining == added == 0
    return keys


def intervals(region):
    return {(path,n) for path,start,end in region for n in range(start,end+1)}


def grouped_interval(rows, kind):
    buckets = collections.defaultdict(list)
    for row in rows:
        buckets[row[kind]].append(int(row["arms"]["scope24"]["hit"])-int(row["arms"]["lexical24"]["hit"]))
    groups = list(buckets.values())
    rng = random.Random(1731)
    samples = sorted(mean(d for group in rng.choices(groups,k=len(groups)) for d in group) for _ in range(5000))
    return [samples[124],samples[4874]]


def main():
    locks = load(ROOT/"prediction-lock.json")
    assert all(digest(ROOT/n)==h for n,h in locks["files"].items())
    preds = {(r["instance_id"],r["source"]):r for r in load(ROOT/"predictions.json.gz") if r["panel"]=="independent"}
    saved = {(r["instance_id"],r["source"]):r for r in load(ROOT/"scored.json.gz") if r["panel"]=="independent"}
    old = {}
    for row in parquet.read_table(ISSUES,columns=["instance_id","patch"]).to_pylist():
        if row["instance_id"] not in {k[0] for k in preds}:
            continue
        keys = original_lines(row["patch"])
        assert keys == unidiff_old(row["patch"]), row["instance_id"]
        old[row["instance_id"]] = keys
    out = []
    for trace in load(NEW):
        iid = trace["instance_id"]
        key = iid, trace["source"]
        views = {(v["path"], n) for v in trace["views3"] for n,_ in v["lines"]}
        truth = old[iid]
        arms = {}
        for arm, region in preds[key]["pred"].items():
            chosen = intervals(region)
            assert chosen <= views
            hits = len(chosen & truth)
            arms[arm] = dict(old_lines=hits, hit=hits>0, denominator=len(chosen),
                             core_precision=saved[key]["scores"][arm]["precision"])
        out.append(dict(iid=iid, source=key[1], repo=trace["repo"], gold_lines=len(truth), shown=len(views),
                       reachable=len(views & truth), arms=arms))
    arms = {arm:dict(hits=sum(r["arms"][arm]["hit"] for r in out), old_lines=sum(r["arms"][arm]["old_lines"] for r in out),
                     core_precision_one=sum(r["arms"][arm]["core_precision"]==1 for r in out),
                     core_precision_one_without_old_line=sum(r["arms"][arm]["core_precision"]==1 and not r["arms"][arm]["hit"] for r in out))
            for arm in out[0]["arms"]}
    summary = dict(episodes=len(out), ids=len(old), eligible_ids=sum(bool(x) for x in old.values()),
                   reachable_episodes=sum(bool(r["reachable"]) for r in out), viewed=sum(bool(r["shown"]) for r in out),
                   lines_returned=sum(r["arms"]["first"]["denominator"] for r in out),arms=arms,
                   paired_ci_by_task=grouped_interval(out,"iid"), paired_ci_by_repo=grouped_interval(out,"repo"))
    write("patch-rows.json.gz",out)
    write("patch-results.json",summary)
    print(summary)


if __name__ == "__main__":
    main()

