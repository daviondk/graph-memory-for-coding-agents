"""Single-candidate identity check against the parent and a position-first Git comparator."""
import collections
import gzip
import json
from prepare import ROOT, git, load, save
from predict import front, tag
from route import snapshot, mapped_line, clustered
from score import confident


def parent_sizes(project, before, paths):
    if not paths:
        return {}
    entries = git(project, "ls-tree", "-l", "-z", before, "--", *sorted(paths)).split(b"\0")
    sizes = {}
    for e in entries:
        if e:
            meta, path = e.split(b"\t", 1)
            sizes[path.decode()] = int(meta.split()[-1])
    return sizes


def main():
    queries = {q["case"]: q for q in load("queries.json")}
    labels = {q["case"]: q for q in load("outcomes.json")}
    previous = {q["case"]: q for q in load("routing-cases.json")}
    rankings = collections.defaultdict(list)
    for line in gzip.decompress((ROOT/"rankings.jsonl.gz").read_bytes()).splitlines():
        row = json.loads(line)
        rankings[row["commit"]].append(row)
    cases = []
    for commit, batch in rankings.items():
        q = queries[batch[0]["case"]]
        project, before = q["project"], q["old"]
        old, new, _ = front(project, before, commit)
        newtags = [list(tag(f)) for f in new]
        olds = {tag(f): f for f in old}
        oldbyname = collections.defaultdict(list)
        counts = collections.defaultdict(collections.Counter)
        for f in old:
            oldbyname[f["path"], f["qual"]].append(f)
            counts[f["path"]].update(f["grams"][0])
        sizes = parent_sizes(project, before, {f["path"] for f in new})
        _, mapping = snapshot(project, before, commit)
        for r in batch:
            cid = r["case"]
            origin = tuple(r["origin"])
            path, qual, line = origin
            src = olds[origin]
            gold = labels[cid]["gold"]
            target = newtags.index(gold) if gold is not None else None
            pth, changes = mapping.get(path, (path, []))
            pred = mapped_line(line, changes)
            def position(i):
                p, n, l = newtags[i]
                return (p != pth, abs(l-pred) if p==pth else 10**9,
                        n.split(".")[-1] != qual.split(".")[-1], n.rpartition(".")[0] != qual.rpartition(".")[0], p, n, l)
            hashes = set(sorted(src["grams"][0], key=lambda g: (counts[path][g],g))[:8])
            rare = [len(hashes & f["grams"][0]) for f in new]
            indices = range(len(new))
            git_top = min(indices,key=position) if new else None
            hybrid_top = min(indices,key=lambda i: (-rare[i],position(i))) if new else None
            rank = r["rankings"]["mixed"]
            strength = r["mixed_scores"]
            def diagnose(order):
                accepts = confident([strength[i] for i in order])
                if not accepts:
                    return dict(accepted=False,verified=False,read_bytes=0,lookups=0,survives=False,correct=False)
                idx = order[0]
                f = new[idx]
                key = (f["path"],f["qual"])
                check = key != origin[:2]
                old_match = oldbyname.get(key, [])
                unchanged = bool(check and len(old_match)==1 and old_match[0]["grams"][0] and old_match[0]["grams"][0]==f["grams"][0])
                return dict(accepted=True,verified=not unchanged,read_bytes=sizes.get(key[0],0) if check else 0,
                        lookups=int(check),survives=unchanged,correct=target is not None and idx==target)
            actual = diagnose(rank)
            masked = diagnose([i for i in rank if i!=target]) if target is not None else None
            cases.append(dict(case=cid,commit=commit,project=project,actual=actual,masked=masked,
                    git_position=target is not None and git_top==target,hybrid=target is not None and hybrid_top==target,
                    rarelex=labels[cid]["rank"]["rarelex"]==1,git_name=previous[cid]["git_line"]))
    def stats(rows):
        return dict(n=len(rows),accepted=sum(x["accepted"] for x in rows),verified=sum(x["verified"] for x in rows),
                correct=sum(x["correct"] for x in rows),verified_correct=sum(x["verified"] and x["correct"] for x in rows),
                parent_bytes=sum(x["read_bytes"] for x in rows),parent_lookups=sum(x["lookups"] for x in rows))
    result = dict(n=len(cases),actual=stats([r["actual"] for r in cases]),masked=stats([r["masked"] for r in cases if r["masked"] is not None]),
            top1={k:sum(r[k] for r in cases) for k in ("git_name","git_position","rarelex","hybrid")},
            rare_minus_position_ci=clustered(cases,lambda r:r["rarelex"]-r["git_position"],lambda r:1),
            hybrid_minus_position_ci=clustered(cases,lambda r:r["hybrid"]-r["git_position"],lambda r:1),
            hybrid_minus_rare_ci=clustered(cases,lambda r:r["hybrid"]-r["rarelex"],lambda r:1))
    save("identity-cases.json",cases)
    save("identity-results.json",result)
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    main()
