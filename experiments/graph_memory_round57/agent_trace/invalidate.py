"""Check whether already-observed single-file editor writes permit address-specific invalidation."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import replay
from extract import DEFAULT, HEADER, HERE, digest, read, save
from score import bootstrap

SIZES = (4096, 16384, 65536)
RULES = ("global", "file", "none")


def project_changes(cache_dir):
    source = read(HERE / "sources.json")
    corpus = read(HERE / "prefixes.json.gz")
    out = []
    for trace, pin in zip(corpus, source["sources"]):
        assert (trace["issue"], trace["actor"]) == (pin["issue"], pin["actor"])
        raw = (cache_dir / pin["actor"] / (pin["issue"] + ".json")).read_bytes()
        assert sha256(raw).hexdigest() == pin["sha256"]
        trajectory = json.loads(raw)["trajectory"]
        assert len(trajectory) == len(trace["events"])
        additions = {}
        for i, step in enumerate(trajectory):
            lines = (step.get("action") or "").strip().splitlines()
            if len(lines) < 2 or not re.fullmatch(r"edit\s+\d+\s*:\s*\d+\s*", lines[0]):
                continue
            if lines[-1].strip() != "end_of_edit" or any(l.strip() == "end_of_edit" for l in lines[1:-1]):
                continue
            paths = {PurePosixPath(m[1]) for m in HEADER.finditer(step.get("observation") or "")}
            if len(paths) != 1:
                continue
            p = next(iter(paths))
            if len(p.parts) >= 3 and p.parts[0] == "/" and p.parts[1] in ("testbed", trace["repo"].replace("/", "__")) and ".." not in p.parts:
                assert trace["events"][i] == ["barrier"]
                additions[str(i)] = str(PurePosixPath(*p.parts[2:]))
        out.append({"issue": trace["issue"], "actor": trace["actor"], "edits": additions})
    save(HERE / "edit-addresses.json.gz", out)


def apply(trace, edits, size):
    replay.BUDGET = size
    caches = {m: replay.Cache(False) for m in RULES}
    opens = []
    queries = []
    affected = Counter()
    for i, event in enumerate(trace["events"]):
        if event[0] == "barrier":
            caches["global"].cells.clear()
            path = edits.get(str(i))
            c = caches["file"]
            if path is None:
                c.cells.clear()
            else:
                other = {k: v for k, v in c.cells.items() if k[0] != path}
                affected["selective"] += 1
                affected["preserve_nonempty"] += bool(other)
                affected["evict_nonempty"] += len(other) != len(c.cells)
                c.cells = other
        if len(event) != 3:
            continue
        action, path, lines = event
        q = {"issue": trace["issue"], "actor": trace["actor"], "at": i, "action": action,
             "bytes": sum(line[2] for line in lines), "served": {m: c.serve(path, lines) for m, c in caches.items()}}
        for c in caches.values():
            assert c.insert(path, lines, ()) <= size
        queries.append(q)
        if action == "open":
            opens.append(q)
    return queries, affected


def summarize(rows):
    size = sum(r["bytes"] for r in rows)
    out = {"n": len(rows), "bytes": size, "arms": {}}
    for m in RULES:
        total = [sum(r["served"][m][i] for r in rows) for i in range(3)]
        out["arms"][m] = {"served": total[0], "fraction": total[0] / size, "complete": total[1], "conflicting_lines": total[2]}
    out["paired"] = bootstrap([(r["issue"], r["served"]["file"][0] - r["served"]["global"][0], r["bytes"]) for r in rows])
    out["wins"] = sum(r["served"]["file"][0] > r["served"]["global"][0] for r in rows)
    out["losses"] = sum(r["served"]["file"][0] < r["served"]["global"][0] for r in rows)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", action="store_true")
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT)
    args = parser.parse_args()
    if args.project:
        project_changes(args.archive_dir)
        return
    traces = read(HERE / "prefixes.json.gz")
    edits = read(HERE / "edit-addresses.json.gz")
    saved = {}
    differences = {}
    for size in SIZES:
        queries = []
        counts = Counter()
        for trace, e in zip(traces, edits):
            assert trace["actor"] == e["actor"] and trace["issue"] == e["issue"]
            rows, stats = apply(trace, e["edits"], size)
            counts.update(stats)
            queries.extend(rows)
        opens = [r for r in queries if r["action"] == "open"]
        saved[str(size)] = {"edits": dict(counts), "open": summarize(opens), "all_views": summarize(queries)}
        differences[str(size)] = queries
    assert saved["16384"]["open"]["arms"]["global"]["served"] == read(HERE / "results.json")["cache_open"]["lru"]["served"]
    save(HERE / "invalidation-queries.json.gz", differences)
    save(HERE / "invalidation-results.json", saved)
    save(HERE / "invalidation-seal.json", {p: digest(HERE / p) for p in ("INVALIDATION_RU.md", "invalidate.py", "prefixes.json.gz", "edit-addresses.json.gz", "invalidation-queries.json.gz", "invalidation-results.json")})
    print(saved["16384"]["open"], saved["16384"]["edits"])


if __name__ == "__main__":
    main()
