"""Bounded import-reachability queries across pinned first-parent versions of public repos."""
import ast
import collections
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import time
import warnings
warnings.simplefilter("ignore", SyntaxWarning)

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parents[1] / "memory_session6/validity/mirrors"
ARMS = ("one", "short3", "diverse", "historical")
SKIP = {"tests", "test", "testing", "docs", "doc", "benchmarks", "examples", "example",
        "vendor", "_vendor", "vendored", "third_party", "fixtures", "scripts", "tools",
        "build", "dist", "changelog.d", "benchmark"}
def stable(s):
    return hashlib.sha256(s.encode()).hexdigest()

def git(repo, *args, data=None):
    return subprocess.run(["git", "-C", str(repo), *args], input=data,
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

def module(path):
    parts = path[:-3].split("/")
    if parts[0] in {"src", "lib"}:
        parts = parts[1:]
    if any(p.lower() in SKIP or not p.isidentifier() for p in parts):
        return None
    if not parts or parts[-1] in {"setup", "conftest"} or parts[-1].startswith("test_"):
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or None

def tree(repo, commit):
    items = collections.defaultdict(list)
    for record in git(repo, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not record:
            continue
        header, name = record.split(b"\t", 1)
        path = name.decode("utf-8", "surrogateescape")
        if not path.endswith(".py") or header.split()[0] not in (b"100644", b"100755"):
            continue
        label = module(path)
        if label:
            items[label].append((path, header.split()[2].decode()))
    return {label: entries[0] for label, entries in items.items() if len(entries) == 1}

def imports(data, current, path):
    try:
        root = ast.parse(data)
    except (ValueError, SyntaxError, UnicodeError):
        return None
    package = current.split(".") if path.endswith("/__init__.py") else current.split(".")[:-1]
    names = set()
    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(package):
                    continue
                prefix = package[:len(package) - node.level + 1]
            else:
                prefix = []
            base = ".".join(prefix + ([node.module] if node.module else []))
            if base:
                names.add(base)
                names.update(base + "." + a.name for a in node.names if a.name != "*")
    return sorted(names - {current})

def populate(repo, trees):
    # Batch Git blobs once per project; cost accounting below simulates independent cold queries.
    needed = {(label, path, blob) for snap in trees for label, (path, blob) in snap.items()}
    blobs = sorted({blob for _, _, blob in needed})
    from io import BytesIO
    data = BytesIO(git(repo, "cat-file", "--batch", data=("\n".join(blobs)+"\n").encode())) if blobs else None
    decoded = {}
    for expected in blobs:
        sha, kind, size = data.readline().split()
        assert sha.decode() == expected and kind == b"blob"
        decoded[expected] = data.read(int(size))
        assert data.read(1) == b"\n"
    edges = {(label, path, blob): imports(decoded[blob], label, path) for label, path, blob in needed}
    graphs = []
    for snap in trees:
        graph = {}
        for label, (path, sha) in snap.items():
            raw = edges[label, path, sha]
            graph[label] = tuple(name for name in (raw or []) if name in snap)
        graphs.append(graph)
    return graphs, sum(v is None for v in edges.values()), len(blobs)

def old_paths(graph, s):
    fifo = collections.deque([(s,)])
    grouped = collections.defaultdict(list)
    expanded = set()
    visits = 0
    capped = False
    while fifo:
        path = fifo.popleft()
        if len(path) > 4:
            continue
        if visits == 10000:
            capped = True
            break
        visits += 1
        expanded.add(path[-1])
        for target in graph[path[-1]]:
            if target in path:
                continue
            hop = path + (target,)
            if len(grouped[target]) < 16:
                grouped[target].append(hop)
            if len(hop) <= 4:
                fifo.append(hop)
    return {t: p for t,p in grouped.items() if len(p[0]) >= 3}, len(expanded), capped

def full_truth(graph, s, t):
    if s not in graph or t not in graph:
        return False
    reached = {s}
    for _ in range(4):
        reached |= {v for u in reached for v in graph[u]}
    return t in reached

def choose(paths, history, use_history):
    deps = [frozenset(p[:-1]) for p in paths]
    unique_nodes = sorted(set.union(*(set(x) for x in deps)))
    events = [({n}, 1 / len(unique_nodes)) for n in unique_nodes]
    if use_history and history:
        events += [(event, 1 / len(history)) for event in history]
    weights = [w for _, w in events]
    protected = [{i for i, (event, _) in enumerate(events) if not event & d} for d in deps]
    selected, covered = [], set()
    while len(selected) < min(3, len(paths)):
        # Fixed input order is shortest first, then lexical.
        best = max((i for i in range(len(paths)) if i not in selected),
                   key=lambda i: sum(weights[j] for j in sorted(protected[i] - covered)))
        selected.append(best)
        covered |= protected[best]
    return [paths[i] for i in selected]

def recheck(proofs, old, new, graph, truth):
    """Inspect current manifests first, then minimally re-read modified providers if necessary."""
    def present(node):
        return node in new and old[node][0] == new[node][0]

    def same(node):
        return present(node) and old[node][1] == new[node][1]

    fast = any(all(map(present, p)) and all(map(same, p[:-1])) for p in proofs)
    if fast:
        assert truth, "Invalid blob certificate"
    read = set()

    def check_edges(p):
        if not all(map(present, p)):
            return False
        for u,v in zip(p,p[1:]):
            if not same(u):
                read.add(u)
                if v not in graph[u]:
                    return False
        return True

    verified = fast or any(check_edges(p) for p in proofs)
    if verified:
        assert truth, "Invalid edge certificate"
    s,t = proofs[0][0], proofs[0][-1]
    if not verified:
        # Compact records carry only the witnessed edges, not full old adjacency lists.
        todo = collections.deque([(s,0)] if s in new and t in new else [])
        seen = {s}
        found = False
        while todo and not found:
            u,depth = todo.popleft()
            if depth >= 4:
                continue
            read.add(u)
            for v in graph[u]:
                if v == t:
                    found = True
                    break
                if v not in seen:
                    seen.add(v)
                    todo.append((v,depth+1))
        assert found == truth, "Fallback and independent oracle disagree"
    return {"fast":int(fast), "validated":int(verified), "reads":len(read),
            "edges":sum(len(p)-1 for p in proofs),
            "path_utf8":len(json.dumps(proofs, ensure_ascii=False,separators=(",",":")).encode()),
            "providers":len({n for p in proofs for n in p[:-1]}),
            "proofs":proofs}

def process(entry):
    name, group, repo_dir, head, locked_commits = entry
    repo = Path(repo_dir)
    ids = locked_commits
    assert ids and head == ids[0]
    windows = min(6, (len(ids)-1)//12)
    indices = list(range(0, windows*12+1, 12))
    trees = [tree(repo, ids[i]) for i in indices]
    graphs, errors, blobs = populate(repo, trees)
    history_cache = {}
    def changed(i):
        if i not in history_cache:
            payload = git(repo,"diff","--no-renames","--name-only","-z",ids[i+1],ids[i])
            history_cache[i] = {p.decode("utf-8","surrogateescape") for p in payload.split(b"\0") if p}
        return history_cache[i]
    rows, metadata = [], []
    for window in range(windows):
        ix = indices[window+1]
        before, after = ids[ix], ids[ix-12]
        old, new = trees[window+1], trees[window]
        g,h = graphs[window+1], graphs[window]
        to_module = {path:label for label,(path,_) in old.items()}
        scenarios = [{to_module[p] for p in changed(i) if p in to_module} for i in range(ix,min(ix+24,len(ids)-1))]
        sources = sorted((n for n,neigh in g.items() if neigh),key=lambda n:stable(name+"|"+before+"|"+n))[:24]
        options, visited, truncated = {}, [], 0
        for s in sources:
            grouped, v, capped = old_paths(g,s)
            options.update({(s,t):paths for t,paths in grouped.items()})
            visited.append(v)
            truncated += int(capped)
        queries = sorted(options,key=lambda pair:stable("|".join((name,before,*pair))))[:64]
        metadata.append(dict(before=before,after=after,windows=window,modules=len(g),sources=len(sources),
                             origin_pairs=len(options),sampled=len(queries),capped_sources=truncated,
                             visited_per_source=visited,historical_events=len(scenarios)))
        for s,t in queries:
            paths = options[s,t]
            arms = [paths[:1], paths[:3], choose(paths,scenarios,False), choose(paths,scenarios,True)]
            truth = full_truth(h,s,t)
            rows.append(dict(repo=name,group=group,before=before,after=after,s=s,t=t,truth=int(truth),
                             alternatives=len(paths), **{arm:recheck(p,old,new,h,truth) for arm,p in zip(ARMS,arms)}))
    shard = ROOT/"shards"; shard.mkdir(exist_ok=True)
    out = shard/(name+".jsonl.gz")
    out.write_bytes(gzip.compress(("\n".join(json.dumps(x,sort_keys=True,separators=(",",":")) for x in rows)+"\n").encode(),mtime=0))
    result = dict(repo=name,group=group,rows=len(rows),head=head,unique_blobs=blobs,parse_fail=errors,
                  sha256=hashlib.sha256(out.read_bytes()).hexdigest(),windows=metadata)
    print(name, len(rows), "queries", flush=True)
    return result

def main():
    receipt = ROOT/"input_lock.json"
    if receipt.exists():
        entries = json.loads(receipt.read_text(encoding="utf-8"))
    else:
        entries = []
        for group,folder in [("A",PRIOR),("B",ROOT/"mirrors")]:
            for repo in sorted(folder.iterdir()):
                if not (repo/"HEAD").exists():
                    continue
                ids = git(repo, "rev-list","--first-parent","--max-count=97","HEAD").decode().splitlines()
                entries.append([repo.name,group,str(repo),ids[0],ids])
        assert collections.Counter(e[1] for e in entries) == {"A":12,"B":4}
        receipt.write_text(json.dumps(entries,indent=2),encoding="utf-8")
    start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=3) as workers:
        results=list(workers.map(process,entries))
    meta={"runtime_s":time.perf_counter()-start,"python":sys.version,"git":git(Path(entries[0][2]),"--version").decode().strip(),
          "repositories":results}
    (ROOT/"receipt.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()

