"""Issue forecasts, then consume each observed editor action. A trace never sees another trajectory."""
from collections import Counter, defaultdict, deque
from pathlib import PurePosixPath
import re

from extract import HERE, digest, read, save

BUDGET = 16384
METHODS = ("lru", "frequency", "name", "own", "shared", "recent_equal", "full", "directed")


def words(path):
    return set(re.findall(r"[a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", path).lower()))


class Memory:
    def __init__(self):
        self.recent = {}
        self.visits = Counter()
        self.previous = None
        self.current_index = None
        self.own = defaultdict(lambda: deque(maxlen=2))
        self.live = {}
        self.owners = Counter()
        self.incident = defaultdict(set)
        self.symmetric = defaultdict(Counter)
        self.directed = defaultdict(Counter)
        self.history_cost = Counter()

    def observe(self, path, time):
        prev = self.previous
        if prev is not None and prev != path:
            self.live[time] = (prev, path)
            for a, b in ((prev, path), (path, prev)):
                self.symmetric[a][b] += 1
                self.history_cost[a] += 1
                self.incident[a].add(time)
                old = self.own[a][0] if len(self.own[a]) == 2 else None
                self.owners[time] += 1
                self.own[a].append(time)
                if old is not None:
                    self.owners[old] -= 1
                    if not self.owners[old]:
                        for member in self.live.pop(old):
                            self.incident[member].remove(old)
                        del self.owners[old]
            self.directed[prev][path] += 1
        self.visits[path] += 1
        self.recent[path] = time
        self.previous, self.current_index = path, time

    def predict(self):
        a = self.previous
        if a is None:
            return {m: [] for m in METHODS}, [0, 0, 0], []
        own = list(self.own.get(a, ()))
        shared = sorted(self.incident.get(a, ()))
        recent = shared[-2:]
        assert own == recent
        def votes(events):
            return Counter(q for event in events for q in self.live[event] if q != a)
        av, sv = votes(own), votes(shared)
        aw = words(a)
        def similarity(p):
            pw = words(p)
            return (int(PurePosixPath(p).name == PurePosixPath(a).name), len(aw & pw) / len(aw | pw) if aw | pw else 0)
        scores = {"lru": {}, "frequency": self.visits, "name": {p: similarity(p) for p in self.recent},
                  "own": av, "shared": sv, "recent_equal": av, "full": self.symmetric.get(a, {}),
                  "directed": self.directed.get(a, {})}
        ranked = {m: sorted(self.recent, key=lambda p: (metric.get(p, 0), self.recent[p]), reverse=True)
                  for m, metric in scores.items()}
        return ranked, [len(own), len(shared), self.history_cost[a]], sorted(set(shared) - set(own))


class Cache:
    def __init__(self, graph):
        self.graph = graph
        self.cells = {}
        self.peak = 0
        self.position = 0

    def serve(self, path, lines):
        hits = 0
        count = 0
        conflict = 0
        for num, uid, size in lines:
            stored = self.cells.get((path, num))
            if stored:
                if stored[0] == uid:
                    hits += size
                    count += 1
                else:
                    conflict += 1
        return [hits, int(count == len(lines)), conflict]

    def insert(self, path, lines, ranks):
        for num, uid, size in lines:
            self.position += 1
            self.cells[(path, num)] = (uid, size, self.position)
        order = {p: len(ranks) - i for i, p in enumerate(ranks)}
        def priority(cell):
            file = cell[0][0]
            return (file == path, order.get(file, 0), cell[1][2]) if self.graph else (cell[1][2],)
        candidates = sorted(self.cells.items(), key=priority, reverse=True)
        cells = {}
        used = 0
        for key, value in candidates:
            if used + value[1] <= BUDGET:
                cells[key] = value
                used += value[1]
        self.cells = cells
        self.peak = max(self.peak, used)
        return used


def replay(trace):
    mem = Memory()
    caches = {m: Cache(m == "graph") for m in ("lru", "graph")}
    records = []
    cache_records = []
    barriers = 0
    for t, event in enumerate(trace["events"]):
        action = event[0]
        if action == "barrier":
            barriers += 1
            for cache in caches.values():
                cache.cells.clear()
        if len(event) < 3:
            continue
        # Freeze candidate lists and work before revealing this tool's observed target.
        ranks, cost, extra = mem.predict()
        previous, last = mem.previous, mem.current_index
        path, lines = event[1:]
        size = sum(line[2] for line in lines)
        service = {m: cache.serve(path, lines) for m, cache in caches.items()}
        if action == "open" and previous is not None:
            records.append({"at": t, "previous_at": last, "current": previous, "target": path,
                            "cost": cost, "ranks": ranks, "shared_extra_indices": extra})
        mem.observe(path, t)
        graph_rank = mem.predict()[0]["shared"]
        occupancy = {m: cache.insert(path, lines, graph_rank) for m, cache in caches.items()}
        cache_records.append({"at": t, "action": action, "size": size, "lines": len(lines),
                              "served": service, "occupancy": occupancy})
    return {**{k: trace[k] for k in ("issue", "actor", "repo")}, "predictions": records, "cache": cache_records,
            "barriers": barriers, "peak": {m: c.peak for m, c in caches.items()}}


def main():
    outputs = [replay(t) for t in read(HERE / "prefixes.json.gz")]
    save(HERE / "forecasts.json.gz", outputs)
    names = ["PROTOCOL_RU.md", "sources.json", "prefixes.json.gz", "extract.py", "replay.py", "forecasts.json.gz"]
    save(HERE / "forecast-seal.json", {k: digest(HERE / k) for k in names})
    print(f"Sealed {len(outputs)} trajectories.")


if __name__ == "__main__":
    main()
