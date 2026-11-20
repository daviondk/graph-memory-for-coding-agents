"""Build import proof certificates from source blobs the direct search already opened."""
from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent / "lazy"))
from lazy_git import GitObjects, Snapshot, choose


def first_path(snap, source, target):
    if not snap.resolve(source) or not snap.resolve(target):
        return ()
    queue = deque([(source,)])
    seen = {source}
    while queue:
        path = queue.popleft()
        if len(path) >= 5:
            continue
        for n in snap.neighbors(path[-1]):
            hop = path + (n,)
            if n == target:
                return hop
            if n not in seen:
                seen.add(n)
                queue.append(hop)
    return ()


def visible_paths(edges, source, target, limit):
    queue = deque([(source,)])
    paths = []
    visits = 0
    while queue and visits < 10000:
        path = queue.popleft()
        visits += 1
        for n in edges.get(path[-1], ()):
            if n in path:
                continue
            hop = path + (n,)
            if n == target:
                paths.append(hop)
                if len(paths) == limit:
                    return paths
            elif len(hop) <= 4:
                queue.append(hop)
    return paths


def diverse_paths(paths):
    # Starting with the first witness, protect singleton provider-change scenarios.
    deps = [set(p[:-1]) for p in paths]
    domain = set.union(*deps)
    protected = [domain - d for d in deps]
    used = [0]
    covered = protected[0].copy()
    while len(used) < min(3,len(paths)):
        best = max((i for i in range(len(paths)) if i not in used),
                   key=lambda i:len(protected[i]-covered))
        used.append(best)
        covered |= protected[best]
    return [paths[i] for i in used]


def compact(snap, first, paths, edges):
    # Array format has identical base overhead for all three certificate methods.
    ids = {}
    nodes = []
    def intern(name):
        if name not in ids:
            ids[name] = len(nodes)
            path, oid = snap.modules[name]
            nodes.append((name,path,oid))
        return ids[name]
    pids = [tuple(intern(n) for n in p) for p in paths]
    eids = [(intern(u), intern(v)) for u,v in edges]
    return [snap.commit, first[0], first[-1], nodes, pids, eids]


def as_bytes(obj):
    return json.dumps(obj, ensure_ascii=True, separators=(",",":")).encode()


def adjacency_control(snap, first, budget):
    selected = []
    first_edges = set(zip(first, first[1:]))
    cache = compact(snap,first,[first],selected)
    if len(as_bytes(cache)) == budget:
        return cache
    for u,neigh in snap.edges.items():
        for v in neigh:
            if (u,v) in first_edges:
                continue
            new = compact(snap,first,[first],selected+[(u,v)])
            if len(as_bytes(new)) <= budget:
                selected.append((u,v))
                cache = new
    return cache


def decode(cache):
    old, source, target, nodes, pids, eids = cache
    manifest = {name:(path,oid) for name,path,oid in nodes}
    paths = [tuple(nodes[i][0] for i in p) for p in pids]
    extra = [(nodes[i][0],nodes[j][0]) for i,j in eids]
    seen = dict.fromkeys(edge for path in paths for edge in zip(path,path[1:]))
    for edge in extra:
        seen[edge] = True
    return source, target, manifest, paths, list(seen)


def recall(snap, cache, control=False):
    source,target,manifest,paths,edges = decode(cache)
    def present(n):
        row=snap.resolve(n)
        return row is not None and row[0]==manifest[n][0]
    def same(n):
        return present(n) and snap.resolve(n)[1]==manifest[n][1]
    if control:
        known = defaultdict(list)
        for u,v in edges:
            known[u].append(v)
        # An equal-byte positive-edge cache may combine its saved edges into new paths.
        for ls in known.values():
            ls.sort()
        other=visible_paths(known,source,target,10000)
        paths=paths[:1]+[p for p in other if p!=paths[0]]
    def fresh_path(p):
        return all(present(n) for n in p) and all(same(n) for n in p[:-1])
    if any(fresh_path(p) for p in paths):
        return True, True, True
    def verified_path(p):
        return all(present(n) for n in p) and all(same(u) or v in snap.neighbors(u) for u,v in zip(p,p[1:]))
    if any(verified_path(p) for p in paths):
        return True, False, True
    # A certified cached suffix may close a live BFS prefix. Incomplete static or
    # cached edges never prove absence; all negative results run the full BFS.
    if not snap.resolve(source) or not snap.resolve(target):
        return False, False, False
    rev = defaultdict(list)
    for u,v in edges:
        if present(v) and present(u) and (same(u) or v in snap.edges.get(u,())):
            rev[v].append(u)
    suffix = {target:0}
    todo = deque([target])
    while todo:
        v=todo.popleft()
        if suffix[v]>=4:
            continue
        for u in rev[v]:
            if u not in suffix:
                suffix[u]=suffix[v]+1
                todo.append(u)
    queue=deque([(source,0)])
    seen={source}
    while queue:
        u,depth=queue.popleft()
        if depth+suffix.get(u,99)<=4:
            return True,False,False
        if depth>=4:
            continue
        for v in snap.neighbors(u):
            if depth+1+suffix.get(v,99)<=4:
                return True,False,False
            if v not in seen:
                queue.append((v,depth+1))
                seen.add(v)
    return False,False,False
