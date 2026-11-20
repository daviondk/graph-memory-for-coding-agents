"""Resolve bounded static import reachability and cache witnesses using only named Git objects.

Example: python lazy_git.py REPO OLD NEW source.module target.module --method historical
Any two valid pinned commits may be supplied. No project source is executed.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from run import choose, imports, module  # frozen pure reference semantics

METHODS = ("one", "short3", "diverse", "historical")


class GitObjects:
    def __init__(self, repo):
        self.repo = str(repo)
        self.process = subprocess.Popen(
            ["git", "-C", self.repo, "cat-file", "--batch"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )

    def get(self, sha):
        self.process.stdin.write(sha.encode("ascii") + b"\n")
        self.process.stdin.flush()
        head = self.process.stdout.readline().split()
        if len(head) != 3:
            raise RuntimeError(f"Missing Git object: {sha!r}, reply {head!r}")
        oid, kind, size = head
        size = int(size)
        raw = self.process.stdout.read(size)
        if len(raw) != size or self.process.stdout.read(1) != b"\n":
            raise IOError(f"truncated Git batch reply for {sha!r}")
        return oid.decode("ascii"), kind, raw

    def close(self):
        self.process.stdin.close()
        self.process.stdout.close()
        self.process.wait()


class Snapshot:
    def __init__(self, objects, commit):
        self.objects = objects
        self.trees = {}
        self.blobs = {}
        self.modules = {}
        self.edges = {}
        self.file_reads = []
        self.count = Counter()
        oid, kind, data = objects.get(commit + "^{commit}")
        if kind != b"commit":
            raise ValueError(f"Expected commit: {commit!r}")
        self.commit = oid
        self.oid_bytes = len(oid) // 2
        header = data.split(b"\n", 1)[0].split()
        if header[0] != b"tree":
            raise ValueError("Commit has no root tree")
        self.root = header[1].decode("ascii")
        self.count.update(commit_objects=1, commit_bytes=len(data))

    def directory(self, oid):
        if oid in self.trees:
            self.count["tree_cache_hits"] += 1
            return self.trees[oid]
        _, kind, raw = self.objects.get(oid)
        if kind != b"tree":
            raise ValueError(f"Expected tree: {oid}")
        self.count.update(tree_objects=1, tree_bytes=len(raw))
        entries = {}
        offset = 0
        while offset < len(raw):
            space = raw.index(b" ", offset)
            zero = raw.index(b"\0", space + 1)
            end = zero + 1 + self.oid_bytes
            entries[raw[space + 1:zero]] = raw[offset:space], raw[zero + 1:end].hex()
            offset = end
        self.count["tree_entry_headers_seen"] += len(entries)
        self.trees[oid] = entries
        return entries

    def path(self, path):
        self.count["path_probes"] += 1
        oid = self.root
        parts = path.encode("utf-8", "surrogateescape").split(b"/")
        for i, part in enumerate(parts):
            entry = self.directory(oid).get(part)
            if entry is None:
                return None
            mode, oid = entry
            if i == len(parts) - 1:
                return oid if mode in (b"100644", b"100755") else None
            if mode != b"40000":
                return None

    def resolve(self, name):
        if name in self.modules:
            self.count["module_cache_hits"] += 1
            return self.modules[name]
        self.count["module_lookups"] += 1
        found = []
        suffix = name.replace(".", "/")
        for prefix in ("", "src/", "lib/"):
            for tail in (".py", "/__init__.py"):
                path = prefix + suffix + tail
                if module(path) != name:
                    continue
                oid = self.path(path)
                if oid:
                    found.append((path, oid))
        value = found[0] if len(found) == 1 else None
        self.modules[name] = value
        return value

    def neighbors(self, name):
        if name in self.edges:
            self.count["adjacency_cache_hits"] += 1
            return self.edges[name]
        pos = self.resolve(name)
        if pos is None:
            self.edges[name] = ()
            return ()
        path, oid = pos
        if oid not in self.blobs:
            _, kind, data = self.objects.get(oid)
            if kind != b"blob":
                raise ValueError("Expected regular file blob")
            self.blobs[oid] = data
            self.count.update(blob_objects=1, blob_bytes=len(data))
            self.file_reads.append([name, path, oid])
        else:
            self.count["blob_cache_hits"] += 1
        self.count["providers_parsed"] += 1
        raw_names = imports(self.blobs[oid], name, path)
        if raw_names is None:
            self.count["parse_failures"] += 1
        self.edges[name] = tuple(target for target in raw_names or [] if self.resolve(target))
        return self.edges[name]

    def describe(self):
        return {"counts": dict(self.count), "source_reads": self.file_reads,
                "metadata_tree_oids": sorted(self.trees), "commit": self.commit}


def direct(snapshot, source, target):
    if not snapshot.resolve(source) or not snapshot.resolve(target):
        return False
    queue = deque([(source, 0)])
    seen = {source}
    while queue:
        node, depth = queue.popleft()
        if depth >= 4:
            continue
        for neighbor in snapshot.neighbors(node):
            if neighbor == target:
                return True
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, depth + 1))
    return False


def paths_to(snapshot, source, target, needed):
    if not snapshot.resolve(source) or not snapshot.resolve(target):
        return [], 0, False
    queue = deque([(source,)])
    paths = []
    visits = 0
    while queue:
        if visits == 10000:
            return paths, visits, True
        path = queue.popleft()
        visits += 1
        for neighbor in snapshot.neighbors(path[-1]):
            if neighbor in path:
                continue
            hop = path + (neighbor,)
            if neighbor == target:
                paths.append(hop)
                if len(paths) == needed:
                    return paths, visits, False
            if len(hop) <= 4:
                queue.append(hop)
    return paths, visits, False


def historical_changes(repo, commit, proof_nodes):
    """Read changed file names only. Exclude the empty past across a shallow boundary."""
    def cmd(*args):
        return subprocess.run(["git", "-C", repo, *args], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True).stdout
    chain_raw = cmd("rev-list", "--max-count=25", "--first-parent", commit)
    chain = chain_raw.decode("ascii").splitlines()
    events = []
    total_bytes, paths_seen = 0, 0
    by_path = {path: name for name, (path, _) in proof_nodes.items()}
    for newer, older in zip(chain, chain[1:]):
        raw = cmd("diff", "--no-renames", "--name-only", "-z", older, newer)
        changed = [x.decode("utf8", "surrogateescape") for x in raw.split(b"\0") if x]
        total_bytes += len(raw)
        paths_seen += len(changed)
        events.append({by_path[path] for path in changed if path in by_path})
    return events, {"history_rev_list_calls": 1, "history_rev_list_bytes": len(chain_raw),
                    "history_diff_calls": len(events), "history_diff_name_bytes": total_bytes,
                    "history_changed_paths_seen": paths_seen,
                    "history_commit_chain": chain}


def record(snapshot, source, target, method):
    needed = {"one": 1, "short3": 3, "diverse": 16, "historical": 16}[method]
    paths, visits, capped = paths_to(snapshot, source, target, needed)
    history = {}
    if method in {"diverse", "historical"} and paths:
        relevant = {n: snapshot.resolve(n) for p in paths for n in p[:-1]}
        scenarios = []
        if method == "historical":
            scenarios, history = historical_changes(snapshot.objects.repo, snapshot.commit, relevant)
        selected = choose(paths, scenarios, method == "historical")
    else:
        selected = paths
    manifest = {n: snapshot.resolve(n) for path in selected for n in path}
    return {"source": source, "target": target, "commit": snapshot.commit,
            "proofs": selected, "manifest": manifest}, {"visits": visits,
            "capped": capped, "available_or_requested_paths": len(paths), "history": history}


def check(snapshot, cert):
    proofs, saved = cert["proofs"], cert["manifest"]

    def present(name):
        value = snapshot.resolve(name)
        return value and value[0] == saved[name][0]

    def unchanged(name):
        return present(name) and snapshot.resolve(name)[1] == saved[name][1]

    fast = any(all(present(n) for n in path) and all(unchanged(n) for n in path[:-1])
               for path in proofs)

    def edges_hold(path):
        if not all(present(n) for n in path):
            return False
        return all(unchanged(u) or v in snapshot.neighbors(u) for u, v in zip(path, path[1:]))

    valid = fast or any(edges_hold(path) for path in proofs)
    result = bool(valid) or direct(snapshot, cert["source"], cert["target"])
    return bool(result), bool(fast), bool(valid)


def evaluate(repo, old, new, source, target, methods=METHODS):
    if source == target:
        raise ValueError("Choose different source and target modules")
    obj = GitObjects(repo)
    try:
        out = {}
        for name, commit in (("direct_old", old), ("direct_new", new)):
            tic = perf_counter()
            snap = Snapshot(obj, commit)
            truth = direct(snap, source, target)
            out[name] = dict(outcome=truth, seconds=perf_counter() - tic, **snap.describe())
        for method in methods:
            tic = perf_counter()
            snap = Snapshot(obj, old)
            cert, info = record(snap, source, target, method)
            write = dict(seconds=perf_counter() - tic, **snap.describe(), **info)
            tic = perf_counter()
            snap = Snapshot(obj, new)
            result, fast, valid = check(snap, cert)
            read = dict(seconds=perf_counter() - tic, **snap.describe(), outcome=result,
                        fast=fast, validated=valid)
            out[method] = {"write": write, "read": read, "certificate": cert}
        return out
    finally:
        obj.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "old", "new", "source", "target"):
        parser.add_argument(name)
    parser.add_argument("--method", choices=("all", *METHODS), default="all")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    data = evaluate(args.repo, args.old, args.new, args.source, args.target,
                    METHODS if args.method == "all" else [args.method])
    dump = json.dumps(data, ensure_ascii=True, indent=2)
    if args.out is None:
        print(dump)
    else:
        args.out.write_text(dump + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
