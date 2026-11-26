"""Verify the portable event projection directly against Git commit and tree objects.

Run python verify_long_git.py --cache /path/to/clones (Python 3.9+, Git on PATH).
The directory holds clones named like networkx__networkx, or nested owner/project.
No checkout, network, or Python dependencies are needed. With a different corpus,
pass --pins and --events. With --write-audit store a new summary at the given path.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
from functools import lru_cache
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


@contextmanager
def objects(repo):
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0",
           "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0"}
    args = ["git", "-C", str(repo), "cat-file", "--batch"]
    with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env) as process:
        def read(oid, kind):
            process.stdin.write(oid.hex().encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().split()
            require(len(header) == 3 and header[0] == oid.hex().encode() and header[1] == kind,
                    f"Missing or unexpected {kind!r} object {oid.hex()} in {repo}")
            size = int(header[2])
            data = process.stdout.read(size)
            require(len(data) == size and process.stdout.read(1) == b"\n", "Incomplete Git object")
            digest = hashlib.sha1(kind + b" " + str(size).encode() + b"\0" + data).digest()
            require(digest == oid, f"Git object hash mismatch {oid.hex()}")
            return data
        try:
            yield read
        finally:
            process.stdin.close()
            process.wait()
        require(process.returncode == 0, f"git cat-file exited {process.returncode}")


def commit(read, sha):
    header = read(sha, b"commit").split(b"\n\n", 1)[0].split(b"\n")
    trees = [bytes.fromhex(x[5:].decode()) for x in header if x.startswith(b"tree ")]
    parents = [bytes.fromhex(x[7:].decode()) for x in header if x.startswith(b"parent ")]
    require(len(trees) == 1, f"No single root tree in {sha.hex()}")
    return trees[0], parents


def tree_reader(read):
    @lru_cache(maxsize=2048)
    def tree(oid):
        if oid is None:
            return {}
        raw = read(oid, b"tree")
        children = {}
        pos = 0
        while pos < len(raw):
            separator = raw.index(b" ", pos)
            end = raw.index(b"\0", separator + 1)
            name = raw[separator+1:end]
            mode = int(raw[pos:separator], 8)
            child = raw[end+1:end+21]
            require(len(child) == 20 and name not in children, f"Invalid SHA-1 tree {oid.hex()}")
            children[name] = (mode, child)
            pos = end + 21
        return children
    return tree


def changed_python(tree, before, after):
    pending = [(b"", before, after)]
    changed = set()
    while pending:
        prefix, old, new = pending.pop()
        if old == new:
            continue
        left, right = tree(old), tree(new)
        for name in left.keys() | right.keys():
            a, b = left.get(name), right.get(name)
            if a == b:
                continue
            path = prefix + name
            old_dir = a is not None and a[0] == 0o40000
            new_dir = b is not None and b[0] == 0o40000
            if ((a is not None and not old_dir) or (b is not None and not new_dir)) and path.endswith(b".py"):
                changed.add(path.decode("utf8", "surrogateescape"))
            if old_dir or new_dir:
                pending.append((path + b"/", a[1] if old_dir else None, b[1] if new_dir else None))
    return sorted(changed)


def check(repo, pins, rows):
    require(len(rows) == pins["transitions"], f"Wrong number of stored rows for {repo}")
    stats = Counter()
    with objects(repo) as read:
        tree = tree_reader(read)
        current = bytes.fromhex(pins["head"])
        previous_tree, parents = commit(read, current)
        for i in range(len(rows)-1, -1, -1):
            claimed, paths = rows[i]
            require(current.hex() == claimed, f"Unexpected commit at {repo.name} row {i}")
            require(parents, f"Unanticipated root {claimed}")
            stats["merge_transitions"] += len(parents) > 1
            current = parents[0]
            first_parent_tree, parents = commit(read, current)
            observed = changed_python(tree, first_parent_tree, previous_tree)
            require(observed == paths,
                    f"Path set/order mismatch at {repo.name} row {i} commit {claimed}")
            previous_tree = first_parent_tree
            stats["transitions"] += 1
            stats["changed_python_paths"] += len(paths)
            stats["empty_python_transitions"] += not paths
            stats["over_64_paths"] += len(paths) > 64
        require(current.hex() == pins["boundary"], f"Boundary mismatch in {repo.name}")
        require(stats["over_64_paths"] == pins["large_commits"], f"Wrong oversized count in {repo.name}")
        tree.cache_clear()
    return {"head": pins["head"], "boundary": pins["boundary"], **stats}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--events", type=Path, default=HERE / "long-events.json.gz")
    parser.add_argument("--pins", type=Path, default=HERE / "long-pins.json")
    parser.add_argument("--write-audit", type=Path)
    args = parser.parse_args()

    payload = gzip.decompress(args.events.read_bytes())
    pins_data = args.pins.read_bytes()
    events, pins = json.loads(payload), json.loads(pins_data)
    require(set(events) == set(pins), "Repository key sets differ")
    audit = {"schema": 1, "status": "verified",
             "method": "Git cat-file raw SHA-1 commit ancestry and recursive raw tree diff, no rename inference",
             "events_uncompressed_sha256": hashlib.sha256(payload).hexdigest(),
             "pins_sha256": hashlib.sha256(pins_data).hexdigest(), "projects": {}}
    for name, lock in sorted(pins.items()):
        choices = [args.cache / name.replace("/", "__"), args.cache / name]
        repo = next((p for p in choices if p.is_dir()), None)
        require(repo is not None, f"Missing {name} in {args.cache}")
        audit["projects"][name] = check(repo, lock, events[name])
    audit["total_transitions"] = sum(v["transitions"] for v in audit["projects"].values())
    rendered = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if args.write_audit:
        args.write_audit.write_bytes(rendered.encode("utf8"))
    print(rendered, end="")


if __name__ == "__main__":
    main()
