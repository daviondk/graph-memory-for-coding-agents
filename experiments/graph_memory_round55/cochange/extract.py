"""Select chronological path sets, without downloading blob contents or executing any repo code."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
R54 = HERE.parents[1] / "graph_memory_round54"
sys.path.insert(0, str(R54 / "git_history"))
from inventory import MIRRORS

def git(repo, *args):
    command = ["git", "-C", str(repo), *args]
    return subprocess.check_output(command, timeout=160, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})

def read_json(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)

def write_json(path, data, check):
    dense = path.suffix == ".gz"
    raw = (json.dumps(data, ensure_ascii=True, sort_keys=True, indent=None if dense else 2,
                      separators=(",", ":") if dense else None) + "\n").encode()
    if dense:
        raw = gzip.compress(raw, mtime=0)
    if check:
        assert raw == path.read_bytes(), str(path)
    else:
        path.write_bytes(raw)

def extract(project, head, scratch, offline):
    mirror = MIRRORS.get(project)
    external = scratch / project.replace("/", "__")
    if not offline:
        external.mkdir(parents=True, exist_ok=True)
        if not (external / "HEAD").exists():
            git(external, "init", "--bare", "--quiet")
            git(external, "remote", "add", "origin", f"https://github.com/{project}.git")
            git(external, "config", "remote.origin.promisor", "true")
            git(external, "config", "remote.origin.partialclonefilter", "blob:none")
        try:
            git(external, "rev-parse", "--verify", head + "^{commit}")
        except subprocess.CalledProcessError:
            git(external, "-c", "protocol.version=2", "fetch", "--quiet", "--no-tags", "--depth=640",
                "--filter=blob:none", "origin", head)
        mirror = external
    history = git(mirror, "rev-list", "--first-parent", "-n", "577", head).decode().splitlines()
    assert history[0] == head and len(history) > 65
    # Always drop the oldest selected commit: its parent may be a shallow boundary.
    revisions = list(reversed(history[:-1]))
    parents = list(reversed(history[1:]))
    raw = git(mirror, "log", "--first-parent", "--diff-merges=first-parent", "-z", "--name-only",
              "--no-renames", "--format=%x00CI%H%x00", "-n", str(len(revisions)), head)
    parts = re.split(rb"\x00CI([0-9a-f]{40})\x00", raw)
    assert not parts[0]
    seen = {}
    for rev, payload in zip(parts[1::2], parts[2::2], strict=True):
        # Git separates the format from the first name with NUL LF, even with -z.
        payload = payload.removeprefix(b"\x00").removeprefix(b"\n")
        paths = {name for name in payload.split(b"\x00") if name.endswith(b".py")}
        seen[rev.decode()] = paths
    assert set(seen) == set(revisions)
    # Check a second parser against explicit commit pairs, including empty changes and merges.
    for k in sorted(set([0, len(revisions)-1, *range(0, len(revisions), 23)])):
        confirm = git(mirror, "diff", "--name-only", "--no-renames", "-z", parents[k], revisions[k], "--", "*.py")
        assert set(confirm.rstrip(b"\0").split(b"\0")) - {b""} == seen[revisions[k]], (project, revisions[k])
    rows = [[rev, sorted(path.decode("utf8", "surrogateescape") for path in seen[rev])] for rev in revisions]
    print(project, len(rows), flush=True)
    return project, {"head": head, "base_parent": parents[0], "revisions": rows}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--offline", action="store_true", help="Use original mirrors if they have the same depth.")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    source = read_json(R54 / "git_history" / "registration.json")["projects"]
    with ThreadPoolExecutor(max_workers=2) as group:
        jobs = [group.submit(extract, name, src["commits"][-1], args.scratch, args.offline)
                for name, src in source.items()]
        streams = dict(job.result() for job in jobs)
    artifact = HERE / "commits.json.gz"
    write_json(artifact, streams, args.verify)
    print(hashlib.sha256(artifact.read_bytes()).hexdigest())

if __name__ == "__main__":
    main()
