"""Materialize only first-parent commit/path events. Blob contents are never used."""
import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[1] / "graph_memory_round1" / "git_prediction"
OLD_RAW = Path("D:/CodexResearch/x20-bench-workspace/work/graph_memory_round1/git_prediction")
ROSTER = ("pallets/itsdangerous", "python-hyper/h2", "facelessuser/soupsieve", "tqdm/tqdm",
          "dateutil/dateutil", "pytest-dev/iniconfig", "python-semver/python-semver",
          "pyca/bcrypt", "marshmallow-code/apispec", "agronholm/anyio")
DEFAULT_CACHE = Path("D:/CodexResearch/x20-r55-partner-clock")
ENV = {**os.environ, "GIT_TERMINAL_PROMPT":"0", "GIT_LFS_SKIP_SMUDGE":"1"}

def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], env=ENV, timeout=180)

def dump(path, data):
    content = (json.dumps(data, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
    if path.suffix == ".gz":
        content = gzip.compress(content, mtime=0)
    path.write_bytes(content)

def read_changes(repo, commits):
    interval = commits[0] + ".." + commits[-1]
    rows = git(repo, "log", "--first-parent", "--diff-merges=first-parent", "--no-renames",
               "--name-status", "-z", "--format=%x00@@%H%x00", interval)
    events = []
    for raw in re.split(rb"\x00@@(?=[a-f0-9]{40}\x00)", rows)[1:]:
        sha, raw_paths = raw.split(b"\x00", 1)
        terms = raw_paths.strip(b"\x00").split(b"\x00") if raw_paths.strip(b"\x00") else []
        assert len(terms) % 2 == 0
        active, deleted = [], []
        for code, name in zip(terms[::2], terms[1::2]):
            code = code.strip()
            assert code in {b"A", b"M", b"D", b"T"}
            if name.endswith(b".py"):
                (deleted if code == b"D" else active).append(name.decode("utf-8", "surrogateescape"))
        events.append([sha.decode(), sorted(active), sorted(deleted)])
    events.reverse()
    assert [e[0] for e in events] == commits[1:]
    return events

def fresh_mirror(name, cache, pinned):
    repo = cache / name.replace("/", "__")
    url = "https://github.com/" + name + ".git"
    if not repo.exists():
        subprocess.run(["git", "clone", "--bare", "--single-branch", "--depth=420", "--no-tags",
                        "--filter=blob:none", url, str(repo)], check=True, env=ENV, timeout=200)
    head = pinned or git(repo, "rev-parse", "HEAD").decode().strip()
    for i in range(6):
        revs = git(repo, "rev-list", "--first-parent", "-n", "401", head).decode().splitlines()
        if len(revs) == 401 or git(repo, "rev-parse", "--is-shallow-repository").strip() == b"false":
            break
        git(repo, "fetch", "--deepen=420", "--no-tags", "origin", head)
    return repo, head, list(reversed(revs))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("panel", choices=["development", "external"])
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = ap.parse_args()
    pins_path = HERE / (args.panel + "-pins.json")
    locked = json.loads(pins_path.read_bytes()) if pins_path.exists() else {}
    args.cache.mkdir(parents=True, exist_ok=True)
    events, pins = {}, {}
    if args.panel == "development":
        for tag in ("transfer", "exposure"):
            for p in json.loads((OLD_RAW / (tag+"_pins.json")).read_bytes()):
                if 'sha' not in p:
                    print('No archived input', p['repo'])
                    continue
                name = p["repo"].replace("__", "/")
                repo = OLD_RAW / (tag+"_mirrors") / p["repo"]
                head = p["sha"]
                commits = git(repo, "rev-list", "--first-parent", head).decode().splitlines()[::-1]
                assert len(commits) == p["n_first_parent"]
                events[name] = read_changes(repo, commits)
                pins[name] = [commits[0], head, len(commits)-1]
    else:
        for name in ROSTER:
            repo, head, commits = fresh_mirror(name, args.cache, locked.get(name, [None,None])[1])
            events[name] = read_changes(repo, commits)
            pins[name] = [commits[0], head, len(commits)-1]
            print(name, len(commits)-1, flush=True)
    if locked:
        assert locked == pins
    dump(pins_path, pins)
    dump(HERE / (args.panel + "-events.json.gz"), events)
    print(len(events), sum(map(len, events.values())))

if __name__ == "__main__":
    main()
