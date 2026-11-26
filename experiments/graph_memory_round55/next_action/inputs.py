"""Extract only observable fields from the pinned strict-context trajectories."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
R54 = HERE.parents[1] / "graph_memory_round54"
ARCHIVE = "agent_retrieval_bench_gpt54mini_strict_context_trajectories.tar.zst"
DEFAULT_ARCHIVE = Path("D:/CodexResearch/x20-r54-trace-choice") / ARCHIVE
TASKS = ("code2test", "comment2context", "trace2code")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def save(name, payload):
    raw = (json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()
    dest = HERE / name
    dest.write_bytes(gzip.compress(raw, mtime=0) if name.endswith(".gz") else raw)


def address(repo, path):
    return hashlib.sha256((repo + "\0" + path).encode()).hexdigest()


def project(archive):
    source = R54 / "next_read"
    seal = read(source / "decision-seal.json")
    assert digest(archive) == seal["sources"][ARCHIVE]
    learned = R54 / "learned_read"
    projection = read(learned / "projection.json.gz")
    assert digest(learned / "projection.json.gz") == read(learned / "registration.json")["projection"]
    context = read(source / "explicit-decisions.json.gz")
    assert digest(source / "explicit-decisions.json.gz") == read(source / "explicit-seal.json")["decisions"]
    result = {}
    with tarfile.open(archive) as tree:
        for member in tree:
            if not member.isfile() or "/traces_" not in member.name:
                continue
            trace = json.load(tree.extractfile(member))
            q = trace["sample_id"]
            if q not in projection:
                continue
            assert q not in result
            old, ctx = projection[q], context[q]
            repo = trace["repo"]
            assert repo == old["group"] == ctx["repo"] and trace["base_commit"] == ctx["commit"]
            paths = set(old["paths"])
            actions = [step["parsed"] for step in trace["actions"] if isinstance(step.get("parsed"), dict)]
            finals = [x["suggested_unread_files"] for x in actions if x.get("action") == "final"]
            assert finals
            terminal_augmented = finals[-1] != trace["suggested_unread_files"]
            finals[-1] = trace["suggested_unread_files"]
            eligible = []
            for proposals in finals:
                ordered = dict.fromkeys(address(repo, p) for p in proposals)
                eligible.append([p for p in ordered if p in paths])
            assert eligible[-1] == ctx["new_suggestions"]
            counts = [len(ctx["opened"]), len(ctx["strict"]), len(eligible[-1]), len(finals),
                      sum(s.get("action") == "search" for s in actions),
                      sum(s.get("action") == "read" for s in actions)]
            query = json.dumps(trace["query"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            assert ctx["task"] in TASKS
            result[q] = dict(repo=repo, commit=ctx["commit"], task=ctx["task"], counts=counts,
                             proposals=eligible, terminal_augmented=terminal_augmented, query_hash=hashlib.sha256(query.encode()).hexdigest())
    assert set(result) == set(projection)
    save("observations.json.gz", result)
    save("registration.json", {
        "protocol": digest(HERE / "PROTOCOL_RU.md"), "extractor": digest(HERE / "inputs.py"),
        "model": digest(HERE / "predict.py"), "evaluator": digest(HERE / "grade.py"),
        "projection": digest(learned / "projection.json.gz"), "archive": digest(archive),
        "observations": digest(HERE / "observations.json.gz"), "fit": digest(learned / "evaluate.py"),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    project(parser.parse_args().archive)
