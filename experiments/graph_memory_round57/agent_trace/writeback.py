"""Evaluate saving the observed tool response after a successful single-file edit on a fixed replay."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import replay
from extract import DEFAULT, HEADER, LINE, HERE, digest, read, save
from invalidate import SIZES
from score import bootstrap


def extract_edits(cache_dir):
    source = read(HERE / "sources.json")
    corpus = read(HERE / "prefixes.json.gz")
    scopes = read(HERE / "edit-addresses.json.gz")
    output = []
    for trace, pin, scope in zip(corpus, source["sources"], scopes):
        raw = (cache_dir / pin["actor"] / (pin["issue"] + ".json")).read_bytes()
        assert sha256(raw).hexdigest() == pin["sha256"]
        traj = json.loads(raw)["trajectory"]
        uid = {}
        def get_lines(text, header):
            result = []
            for line in text[header.end():].splitlines():
                m = LINE.fullmatch(line)
                if m:
                    b = (m[2] + "\n").encode("utf-8")
                    result.append([int(m[1]), uid.setdefault(b, len(uid)), len(b)])
            return result
        # Give identical literal strings the same opaque ID as in the sealed read projection.
        for i, event in enumerate(trace["events"]):
            if len(event) == 3:
                obs = traj[i]["observation"]
                assert get_lines(obs, HEADER.search(obs)) == event[2]
        additions = {}
        for index, path in scope["edits"].items():
            text = traj[int(index)]["observation"]
            heads = list(HEADER.finditer(text))
            if len(heads) != 1 or not text.rstrip().splitlines()[-1].startswith("File updated"):
                continue
            lines = get_lines(text, heads[0])
            if lines and all(b[0] == a[0] + 1 for a, b in zip(lines, lines[1:])):
                additions[index] = [path, lines]
        output.append({"issue": trace["issue"], "actor": trace["actor"], "edits": additions})
    save(HERE / "write-observations.json.gz", output)


def play(trace, scoped, edits, size):
    replay.BUDGET = size
    caches = {m: replay.Cache(False) for m in ("read_only", "refresh", "window")}
    grouped = replay.Cache(True)
    last_files = {}
    previously_read = set()
    counted = Counter()
    rows = []
    for i, event in enumerate(trace["events"]):
        idx = str(i)
        if event[0] == "barrier":
            grouped.cells.clear()
            for cache in caches.values():
                if idx in scoped:
                    cache.cells = {k: v for k, v in cache.cells.items() if k[0] != scoped[idx]}
                else:
                    cache.cells.clear()
        if idx in edits:
            path, lines = edits[idx]
            assert path == scoped[idx] and event == ["barrier"]
            old = [r for r in lines if (path, r[0]) in previously_read]
            counted["successful_windows"] += 1
            for method, batch in (("refresh", old), ("window", lines)):
                counted[method + "_edit_input_bytes"] += sum(r[2] for r in batch)
                if batch:
                    caches[method].insert(path, batch, ())
        if len(event) == 3:
            action, path, lines = event
            trials = {m: cache.serve(path, lines) for m, cache in caches.items()}
            trials["group_lru"] = grouped.serve(path, lines)
            rows.append({"issue": trace["issue"], "actor": trace["actor"], "action": action, "at": i,
                         "bytes": sum(r[2] for r in lines), "served": trials})
            previously_read.update((path, r[0]) for r in lines)
            last_files[path] = i
            grouped.insert(path, lines, sorted(last_files, key=last_files.get, reverse=True))
            for c in caches.values():
                c.insert(path, lines, ())
    return rows, counted


def score(rows):
    metrics = {}
    for m in ("read_only", "refresh", "window", "group_lru"):
        metrics[m] = [sum(r["served"][m][i] for r in rows) for i in range(3)]
    contrasts = {}
    for a, b in (("window", "read_only"), ("refresh", "read_only"), ("window", "refresh")):
        pairs = [(r["issue"], r["served"][a][0] - r["served"][b][0], r["bytes"]) for r in rows]
        contrasts[a + "__" + b] = {**bootstrap(pairs), "win": sum(x[1] > 0 for x in pairs),
                                    "loss": sum(x[1] < 0 for x in pairs), "winning_issues": len({x[0] for x in pairs if x[1] > 0})}
    return {"n": len(rows), "bytes": sum(r["bytes"] for r in rows), "arms": metrics, "contrasts": contrasts}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", action="store_true")
    p.add_argument("--archive-dir", type=Path, default=DEFAULT)
    args = p.parse_args()
    if args.project:
        extract_edits(args.archive_dir)
        return
    traces = read(HERE / "prefixes.json.gz")
    scope = read(HERE / "edit-addresses.json.gz")
    active = read(HERE / "write-observations.json.gz")
    scores = {}
    outcomes = {}
    original = read(HERE / "forecasts.json.gz")
    for size in SIZES:
        total = []
        counts = Counter()
        grouping = []
        for t, s, active_edits, prev in zip(traces, scope, active, original):
            assert t["issue"] == s["issue"] == active_edits["issue"] == prev["issue"]
            scope_ = s["edits"]
            rows, counted = play(t, scope_, active_edits["edits"], size)
            if size == 16384:
                for r, old in zip(rows, prev["cache"], strict=True):
                    assert r["at"] == old["at"] and r["bytes"] == old["size"]
                    grouping.append((t["issue"], old["served"]["graph"][0] - r["served"]["group_lru"][0], r["bytes"]))
            total.extend(rows)
            counts.update(counted)
        outcomes[str(size)] = total
        opened = [r for r in total if r["action"] == "open"]
        scores[str(size)] = {"counts": dict(counts), "open": score(opened), "all": score(total)}
        scores[str(size)]["actors_open"] = {a: score([r for r in opened if r["actor"] == a]) for a in sorted({r["actor"] for r in opened})}
        if grouping:
            scores[str(size)]["graph_minus_group_lru_all_views"] = bootstrap(grouping)
    save(HERE / "writeback-results.json", scores)
    save(HERE / "writeback-events.json.gz", outcomes)
    save(HERE / "writeback-seal.json", {p: digest(HERE / p) for p in ("WRITEBACK_RU.md", "writeback.py", "write-observations.json.gz", "writeback-results.json", "writeback-events.json.gz")})
    print(scores["16384"]["open"])
    print(scores["16384"]["counts"], scores["16384"]["graph_minus_group_lru_all_views"])


if __name__ == "__main__":
    main()
