#!/usr/bin/env python3
"""Recompute every headline in this bundle from results/instances.jsonl alone.

Stdlib only, no model download, no network. If this disagrees with README.md, the README is
wrong. That is the point of shipping the candidate lists.

Usage:  python3 tools/verify_bundle.py [bundle_dir]
"""
import json
import os
import sys
from collections import defaultdict

d = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
recs = [json.loads(l) for l in open(os.path.join(d, "results/instances.jsonl"))]

ids = [r["id"] for r in recs]
assert len(ids) == len(set(ids)), "duplicate instance ids: %d rows, %d distinct" % (len(ids), len(set(ids)))

# The rank we report must be recoverable from the candidate list we shipped. 71 instances have
# several gold files and the rank is the best of them, so match against all of them.
checked = mismatch = 0
examples = []
for r in recs:
    if not r["candidates"]:
        continue
    golds = r.get("gold_files") or [r["gold"].rsplit(":", 1)[0]]
    found = 0
    for i, c in enumerate(r["candidates"], 1):
        # Candidate sources carry a checkout prefix the gold path does not.
        if any(c["source"].endswith(g) for g in golds):
            found = i
            break
    checked += 1
    if found != r["rank"]:
        mismatch += 1
        if len(examples) < 5:
            examples.append((r["id"], r["rank"], found, r["n_gold"]))

def agg(rs, label):
    n = len(rs)
    r1 = sum(1 for r in rs if r["rank"] == 1)
    fl = sum(1 for r in rs if r["floor_rank"] == 1)
    gp = sum(1 for r in rs if r["grep_file"])
    ce = sum(1 for r in rs if r["rank"] > 0)
    print("%-26s %4d  %3d %.3f  %3d %.3f  %3d %.3f  %4d %.3f"
          % (label, n, r1, r1 / n, fl, fl / n, gp, gp / n, ce, ce / n))

print("instances %d, distinct %d, K=%s, row bits=%s, machines=%s"
      % (len(recs), len(set(ids)),
         sorted({r["K"] for r in recs}), sorted({r["store"]["bits"] for r in recs}),
         sorted({r["machine"] for r in recs if r["machine"]})))
print("gold rank recomputed from the shipped candidate list: %d checked, %d disagree"
      % (checked, mismatch))
for ex in examples:
    print("   %-28s reported %-3s recomputed %-3s n_gold=%s" % ex)
print()
print("%-26s %4s  %9s  %9s  %9s  %10s" % ("repository", "n", "recall@1", "floor@1", "grep", "ceiling"))
byrepo = defaultdict(list)
for r in recs:
    byrepo[r["repo"]].append(r)
for repo, rs in sorted(byrepo.items(), key=lambda kv: -len(kv[1])):
    agg(rs, repo)
print("-" * 74)
agg(recs, "POOLED")
