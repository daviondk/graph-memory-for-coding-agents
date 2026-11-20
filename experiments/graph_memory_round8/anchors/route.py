"""Replay selective file reads and an exploratory line-mapping comparator."""
import collections
import gzip
import json
import random
import re
from prepare import ROOT, git, load, save
from score import confident


def snapshot(project, before, after):
    data = git(project, "diff", "--no-renames", "--diff-filter=ACMT", "--name-only", "-z", before, after, "--", "*.py")
    paths = [s.decode() for s in data.split(b"\0") if s and not any(t in s.lower() for t in (b"vulnerab", b"exploit", b"malware", b"secret_key_agreement"))]
    sizes = {}
    if paths:
        for entry in git(project, "ls-tree", "-l", "-z", after, "--", *paths).split(b"\0"):
            if entry:
                meta, path = entry.split(b"\t", 1)
                sizes[path.decode()] = int(meta.split()[-1])
    patch = git(project, "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "--no-textconv", "-M", "-U0", before, after, "--", "*.py")
    mapping = {}
    for block in re.split(rb"(?m)^diff --git ", patch)[1:]:
        header = re.split(rb"(?m)^@@ ", block, maxsplit=1)[0]
        src = re.search(rb"(?m)^--- a/(.+)$", header) or re.search(rb"(?m)^rename from (.+)$", header)
        dst = re.search(rb"(?m)^\+\+\+ b/(.+)$", header) or re.search(rb"(?m)^rename to (.+)$", header)
        if not src or not dst:
            continue
        changes = []
        for h in re.finditer(rb"(?m)^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", block):
            a, na, b, nb = h.groups()
            changes.append((int(a), int(na or 1), int(b), int(nb or 1)))
        mapping[src[1].decode()] = (dst[1].decode(), changes)
    return sizes, mapping


def mapped_line(line, changes):
    shift = 0
    for old, n_old, new, n_new in changes:
        if n_old and old <= line < old + n_old:
            return max(1, new + min(line - old, max(0, n_new - 1)))
        if old + n_old <= line and (n_old or old < line):
            shift += n_new - n_old
    return max(1, line + shift)


def clustered(rows, numerator, denominator):
    sums = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        pair = sums[r["commit"]]
        pair[0] += numerator(r)
        pair[1] += denominator(r)
    values = list(sums.values())
    rng = random.Random(81173)
    dist = []
    for _ in range(10000):
        draw = rng.choices(values, k=len(values))
        a, b = map(sum, zip(*draw))
        if b:
            dist.append(a / b)
    dist.sort()
    return [dist[int((len(dist)-1)*q)] for q in (0.025, 0.975)]


def main():
    metas = {q["case"]: q for q in load("queries.json")}
    gold = {q["case"]: q for q in load("outcomes.json")}
    pools = json.loads(gzip.decompress((ROOT/"pools.json.gz").read_bytes()))
    snapshots = {}
    rows = []
    for s in gzip.decompress((ROOT/"rankings.jsonl.gz").read_bytes()).splitlines():
        r = json.loads(s)
        case, commit = r["case"], r["commit"]
        if commit not in snapshots:
            snapshots[commit] = snapshot(r["project"], metas[case]["old"], commit)
        sizes, mapping = snapshots[commit]
        pool = pools[commit]
        assert len(sizes) == pool["stats"]["current_files"]
        p = pool["candidates"]
        old, qual, line = r["origin"]
        scores = r["mixed_scores"]
        common = r["rankings"]["mixed"]
        local = [i for i in common if p[i][0] == old]
        done = confident([scores[i] for i in local])
        goldtag = gold[case]["gold"]
        target = p.index(goldtag) if goldtag is not None else None
        local_without = [i for i in local if i != target]
        selected = local if done else common
        pred_path, changes = mapping.get(old, (old, []))
        line2 = mapped_line(line, changes)
        def tie(i):
            path, name, actual = p[i]
            return (name.split(".")[-1] != qual.split(".")[-1], path != pred_path,
                    name.rpartition(".")[0] != qual.rpartition(".")[0],
                    abs(actual-line2) if path==pred_path else 10**9, p[i])
        g = min(common, key=tie) if common else None
        def hit(order):
            return bool(order and target is not None and order[0] == target)
        rows.append(dict(case=case, commit=commit, project=r["project"], goal_present=target is not None,
            address=gold[case]["rank"]["address"]==1, rarelex=gold[case]["rank"]["rarelex"]==1,
            git_line=target is not None and g==target, full=hit(common), local=hit(local), gated=hit(selected), stop_local=done,
            masked_local_confidence=confident([scores[i] for i in local_without]) if target is not None else None,
            any_support=bool(scores and max(scores)>0), old_bytes=sizes.get(old,0),old_files=int(old in sizes),
            all_bytes=sum(sizes.values()), all_files=len(sizes), gate_bytes=sizes.get(old,0) if done else sum(sizes.values()),
            gate_files=int(old in sizes) if done else len(sizes)))
    agg={k:sum(x[k] for x in rows) for k in ("address","rarelex","git_line","full","local","gated","stop_local","any_support",
            "old_bytes","old_files","all_bytes","all_files","gate_bytes","gate_files")}
    agg.update(n=len(rows),n_commits=len(snapshots), masked_local_confidence=sum(x["masked_local_confidence"] or 0 for x in rows),
            mask_den=sum(x["goal_present"] for x in rows), gated_loses=sum(x["full"] and not x["gated"] for x in rows),
            gated_wins=sum(x["gated"] and not x["full"] for x in rows),
            rare_minus_git_wins=sum(x["rarelex"] and not x["git_line"] for x in rows),
            rare_minus_git_losses=sum(x["git_line"] and not x["rarelex"] for x in rows),
            gate_minus_full_ci=clustered(rows, lambda x: x["gated"]-x["full"],lambda x:1),
            bytes_saved_ci=clustered(rows, lambda x: x["all_bytes"]-x["gate_bytes"],lambda x:x["all_bytes"]),
            rare_minus_git_ci=clustered(rows,lambda x:x["rarelex"]-x["git_line"],lambda x:1))
    save("routing-cases.json",rows)
    save("routing-results.json",agg)
    print(json.dumps(agg,indent=2))
if __name__=="__main__":
    main()
