"""Post-hoc comparison to projection of all old lines untouched by Git hunks."""
import collections
import gzip
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prepare import ROOT, hashbytes, load
from predict import front, tag
from route import clustered, mapped_line, snapshot


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf8")


def tests():
    fixtures = [
        ([(0, 0, 1, 3)], {1: 4, 3: 6}),
        ([(2, 0, 3, 2)], {1: 1, 2: 2, 3: 5, 4: 6}),
        ([(2, 2, 1, 0)], {1: 1, 4: 2, 5: 3}),
        ([(2, 1, 2, 3)], {1: 1, 2: 2, 3: 5}),
        ([(1, 0, 2, 1), (4, 1, 5, 2)], {1: 1, 2: 3, 3: 4, 4: 5, 5: 7}),
    ]
    for changes, answers in fixtures:
        assert all(mapped_line(line, changes) == answer for line, answer in answers.items())


def rank(src, pool, mapping, counts):
    source_path, source_qual, first = tag(src)
    newpath, hunks = mapping[source_path]
    oldlines = [line for line in range(first, src["end"] + 1)
                if not any(old <= line < old + oldcount for old, oldcount, _, _ in hunks)]
    projected = [mapped_line(line, hunks) for line in oldlines]
    projected_header = mapped_line(first, hunks)
    hashes = set(sorted(src["grams"][0], key=lambda v: (counts[v], v))[:8])
    orders = collections.defaultdict(list)
    for i, f in enumerate(pool):
        path, qual, line = tag(f)
        other_file = path != newpath
        other_name = f["name"] != src["name"]
        other_owner = qual.rpartition(".")[0] != source_qual.rpartition(".")[0]
        dist = 10**9 if other_file else abs(line - projected_header)
        votes = 0 if other_file else sum(line <= n <= f["end"] for n in projected)
        header_miss = dist != 0
        addr = (other_name, other_file, other_owner, dist, tag(f))
        pos = (other_file, dist, other_name, other_owner, tag(f))
        whole = (-votes, header_miss, addr)
        lex = -len(hashes & f["grams"][0])
        for method, priority in [
            ("git_name", addr), ("git_position", pos), ("git_exact", (header_miss, addr)),
            ("git_range", whole), ("git_header_range", (header_miss, -votes, addr)),
            ("hybrid_position", (lex, pos)), ("hybrid_range", (lex, whole)),
        ]:
            orders[method].append((priority, i))
    return {method: min(priorities)[1] for method, priorities in orders.items()}, len(projected)


def summarize(rs):
    arms = ("git_name", "git_position", "git_exact", "git_range", "git_header_range", "rarelex", "hybrid_position",
            "hybrid_range")
    result = dict(n=len(rs), clusters=len({r["commit"] for r in rs}),
                  hit={method: sum(r[method] for r in rs) for method in arms}, pairs={})
    for arm, base in [("rarelex", "git_range"), ("hybrid_position", "git_range"), ("hybrid_range", "git_range"),
                      ("hybrid_range", "hybrid_position")]:
        a = sum(r[arm] and not r[base] for r in rs)
        b = sum(r[base] and not r[arm] for r in rs)
        bounds = clustered(rs, lambda r: r[arm] - r[base], lambda r: 1)
        result["pairs"][arm + " minus " + base] = dict(wins=a, losses=b, delta_pp=100*(a-b)/len(rs),
                                                       ci95_commit_pp=[100*x for x in bounds])
    return result


def main():
    tests()
    for name, h in load("prediction-lock.json").items():
        assert hashbytes((ROOT / name).read_bytes()) == h
    queries = {q["case"]: q for q in load("queries.json")}
    external = {r["case"]: r for r in load("identity-cases.json")}
    batches = collections.defaultdict(list)
    for row in load("outcomes.json"):
        q = queries[row["case"]]
        batches[q["project"], q["old"], q["new"]].append(row)

    outcomes = []
    for (project, old, new), batch in batches.items():
        older, current, _ = front(project, old, new)
        _, mapping = snapshot(project, old, new)
        by_old = {tag(f): f for f in older}
        by_current = {tag(f): f for f in current}
        module_counts = collections.defaultdict(collections.Counter)
        for f in older:
            module_counts[f["path"]].update(f["grams"][0])
        for annotation in batch:
            case = annotation["case"]
            src = by_old[tuple(annotation["origin"])]
            best, used = rank(src, current, mapping, module_counts[src["path"]])
            choices = {k: list(tag(current[ix])) for k, ix in best.items()}
            hit = {k: choice == annotation["gold"] for k, choice in choices.items()}
            assert hit["git_name"] == external[case]["git_name"]
            assert hit["git_position"] == external[case]["git_position"]
            assert hit["hybrid_position"] == external[case]["hybrid"]
            body = "unresolved"
            unique = None
            if annotation["gold"] is not None:
                gold = by_current[tuple(annotation["gold"])]
                body = "equal" if src["grams"][0] == gold["grams"][0] else "changed"
                unique = sum(f["grams"][0] == src["grams"][0] for f in current) == 1
            outcomes.append(dict(case=case, project=project, commit=new, body=body,
                                 original=list(tag(src)), old_end=src["end"], retained_old_lines=used,
                                 unique_old_grams=unique, choices=choices, rarelex=annotation["rank"]["rarelex"]==1, **hit))
    save("range-cases.json", outcomes)
    result = {condition: summarize(selected) for condition, selected in [
        ("all", outcomes), ("changed", [r for r in outcomes if r["body"] == "changed"]),
        ("equal", [r for r in outcomes if r["body"] == "equal"])]}
    save("range-results.json", result)
    save("range-lock.json", {str(p.relative_to(ROOT)): hashbytes(p.read_bytes()) for p in [
        ROOT/"source-lock.json", ROOT/"prediction-lock.json", ROOT/"identity-cases.json", ROOT/"outcomes.json",
        ROOT/"route.py", ROOT/"identity.py", Path(__file__), HERE/"range-cases.json", HERE/"range-results.json"]})
    for condition, x in result.items():
        print(condition, x["n"], x["clusters"], x["hit"], x["pairs"]["hybrid_position minus git_range"])


if __name__ == "__main__":
    main()
