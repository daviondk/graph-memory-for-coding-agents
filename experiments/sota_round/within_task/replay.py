"""Replay each prior mini-SWE-agent history in isolation on one CPU worker."""
import argparse
import gzip
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from memory import ARMS, SUBMIT, Memory, canonical, each_batch, signature

HERE = Path(__file__).resolve().parent
PIN = "11164976b4f920cdb0d0cd570ca572e49acea1e8"
FILES = ("protocol.md", "memory.py", "replay.py", "summarize.py")


def write(f, row):
    f.write(json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n")


def signatures():
    return {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest() for f in FILES}


def population(base):
    root = base / "benchmark"
    info = json.loads((base / "memory-stage-fetch/source-manifest.json").read_bytes())
    assert info["sha"] == PIN
    # Roster only enumerates the same causal union already fed to released run_one.
    maxima = {}
    roster = []
    for p in sorted((base / "memory-stage-audit/raw_bm25").glob("*.json")):
        data = json.loads(p.read_bytes())
        repo = data["repo"].replace("/", "__")
        number = int(data["instance_id"].rsplit("-", 1)[1])
        maxima[repo] = max(number, maxima.get(repo, 0))
        roster.append((repo, number))
    assert len(roster) == 111 and len(maxima) == 90
    specs = []
    for s in info["siblings"]:
        path = s["rfilename"].split("/")
        if len(path) != 5 or not path[-1].endswith(".traj.json") or path[2] not in maxima:
            continue
        if int(path[3].rsplit("-", 1)[1]) < maxima[path[2]] and s["size"] <= 64_000_000:
            specs.append(s)
    assert len(specs) == 2470
    return root, sorted(specs, key=lambda s: s["rfilename"])


def bytes_verified(p, spec):
    raw = p.read_bytes()
    assert len(raw) == spec["size"]
    digest = hashlib.sha256(raw).hexdigest()
    if spec.get("lfs"):
        assert digest == spec["lfs"]["sha256"]
    else:
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == spec["blobId"]
    return raw, digest


def label_reason(steps):
    if not steps:
        return "no_next_command"
    s = steps[0]
    if s.rc is None:
        return "next_status_unknown"
    if s.rc != 0:
        return "next_nonzero"
    if SUBMIT.search(s.cmd):
        return "next_submission"
    return "labelled"


def finish(previous, steps, reason, stream):
    _, _, row, guesses, available = previous
    row["branch"] = reason
    row["sent_bytes"] = {a: [len(r.cmd.encode()) for r in recs] for a, recs in guesses.items()}
    if reason == "labelled":
        gold = canonical(steps[0].cmd)
        fam, target = signature(gold)
        row["gold"] = {"next_batch": row["fail"][0] + 1, "slot": 0, "family": fam, "target": target,
                       "sha256": hashlib.sha256(gold.encode()).hexdigest(), "bytes": len(gold.encode())}
        row["any_success_exact"] = gold in available
        row["any_success_target"] = bool(fam and target and any(signature(x) == (fam,target) for x in available))
        # Bitmask for each returned item: 1 exact command, 2 family+first target, 4 family alone.
        row["hits"] = {}
        for arm, recs in guesses.items():
            flags = []
            for rec in recs:
                pfam, ptarget = signature(rec.cmd)
                exact = rec.cmd == gold
                family = bool(fam and fam == pfam)
                strict = bool(family and target and target == ptarget)
                flags.append(int(exact) + 2 * int(strict) + 4 * int(family))
            row["hits"][arm] = flags
    write(stream, row)


def replay(messages, sid, counts, stream):
    memory = Memory()
    previous = None
    for b, steps in enumerate(each_batch(messages, counts)):
        fail = next((s for s in steps if s.rc is not None and s.rc != 0), None)
        pending = None
        if fail is not None:
            meta, guesses, available = memory.predict(b, fail)
            meta["sid"] = sid
            pending = (b, fail, meta, guesses, available)
            counts["failure_batches"] += 1
        if previous:
            reason = label_reason(steps)
            finish(previous, steps, reason, stream)
            counts[reason] += 1
            if reason == "labelled":
                memory.append_pair(previous[:2], b, steps[0])
        for s in steps:
            memory.append_step(b, s)
        previous = pending
    if previous:
        finish(previous, [], "no_next_decision", stream)
        counts["no_next_decision"] += 1
    return {"stored_bytes": dict(memory.bytes), "pairs": len(memory.full_pair.rows),
            "success": len(memory.success.rows), "all": len(memory.all_steps.rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, default=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench"))
    ap.add_argument("--freeze", action="store_true")
    args = ap.parse_args()
    frozen = HERE / "freeze.json"
    if args.freeze:
        with frozen.open("x", encoding="utf8") as f:
            json.dump({"utc": datetime.now(timezone.utc).isoformat(), "sha256": signatures()}, f, indent=2)
        return
    assert json.loads(frozen.read_bytes())["sha256"] == signatures(), "Frozen code mismatch"
    root, specs = population(args.base)
    start = time.monotonic()
    count = Counter()
    with gzip.open(HERE/"decisions.jsonl.gz", "wt", encoding="utf8", compresslevel=5) as decisions, \
         gzip.open(HERE/"histories.jsonl.gz", "wt", encoding="utf8", compresslevel=5) as histories:
        for i, spec in enumerate(specs, 1):
            path = root / spec["rfilename"]
            raw, checksum = bytes_verified(path, spec)
            data = json.loads(raw)
            del raw
            messages = data if isinstance(data, list) else data["messages"]
            counts = Counter()
            stats = replay(messages, path.parent.name, counts, decisions)
            assert stats["pairs"] == counts["labelled"]
            write(histories, {"path": spec["rfilename"], "sha256": checksum, "source_bytes": spec["size"],
                              "counts": dict(counts), **stats})
            count.update(counts)
            if i % 200 == 0:
                print(f"{i}/{len(specs)} histories {time.monotonic()-start:.1f}s", flush=True)
    (HERE/"run.json").write_text(json.dumps({"python": sys.version, "platform": platform.platform(),
        "elapsed": time.monotonic()-start, "histories": len(specs), "counts": dict(count),
        "sha256": signatures(), "dataset": PIN}, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()
