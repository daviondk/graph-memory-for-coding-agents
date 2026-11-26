"""Online, fixed-window graph replay with bounded exact top-k and before-update prediction."""
import argparse
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import sqlite3
import sys

from extract import HERE, R54, read_json, write_json

sys.path.insert(0, str(R54 / "reserve"))
from reserve_store import key, refresh
from classic import ClassicStore, prefix_step
from partial import certify
from core import NOW

K = 8
WARM = 64
WINDOWS = (16, 32, 64)
CAPS = (8, 9, 12, 13)
RANKERS = ("degree", "frequency", "recency", "anchored")
COST_FIELDS = ["cold_probes", "cold_rows", "warm_probes", "warm_rows"]
QUALITY = ["gold_n", "available_n", "degree_hits", "frequency_hits", "recency_hits", "anchored_hits"]
UPDATE = ["positive_pairs", "negative_pairs", "score_writes", "born", "packet_changed"]

class Controller:
    """Common SQL index; policy receives only birth and changed scores and its own state."""
    def __init__(self, db, capacity, alg):
        self.db = db
        self.capacity = capacity
        self.alg = alg
        self.event = Counter()
        self.state = refresh(db.execute(NOW, ("g", capacity)).fetchall(), capacity)
        self.event.update(cold_probes=1, cold_rows=len(self.state[0]))

    def step(self, dirty):
        self.event.clear()
        if self.alg == "classic":
            prefix, complete = prefix_step(self.state, dirty, self.capacity)
            if not complete and len(prefix) < K:
                self.state = ClassicStore.refill(self, "g", prefix)
            else:
                self.state = (prefix, None if complete else key(prefix[-1]))
        else:
            known, bound, prefix = certify(self.state, dirty, self.capacity)
            if bound is not None and len(prefix) < K:
                self.state = ClassicStore.refill(self, "g", prefix)
            else:
                self.state = (known, bound)
        return self.state[0][:K]

class Graph:
    def __init__(self, db):
        self.db = db
        self.paths = {}
        self.degree = {}
        self.freq = Counter()
        self.last = {}
        self.edges = Counter()
        self.neighbors = defaultdict(dict)

    def put(self, paths, t):
        born = []
        path_ids = []
        for path in paths:
            if path not in self.paths:
                self.paths[path] = len(self.paths)
                born.append(self.paths[path])
                self.degree[self.paths[path]] = 0
            i = self.paths[path]
            self.last[i] = t
            path_ids.append(i)
        self.db.executemany("INSERT INTO source VALUES('g',?,0)", [(i,) for i in born])
        return path_ids, born

    def apply(self, coming, going, t):
        added, born = self.put(coming, t)
        removed = [self.paths[p] for p in going]
        self.freq.update(added)
        self.freq.subtract(removed)
        changes = Counter(combinations(sorted(added), 2))
        changes.subtract(combinations(sorted(removed), 2))
        net = Counter()
        num_positive = num_negative = 0
        for (i, j), delta in changes.items():
            if not delta:
                continue
            num_positive += delta > 0
            num_negative += delta < 0
            weight = self.edges[(i, j)] + delta
            assert weight >= 0
            if weight:
                self.edges[(i, j)] = self.neighbors[i][j] = self.neighbors[j][i] = weight
            else:
                del self.edges[(i, j)], self.neighbors[i][j], self.neighbors[j][i]
            net[i] += delta
            net[j] += delta
        dirty = dict.fromkeys(born, 0)
        for i, delta in net.items():
            if delta:
                self.degree[i] += delta
                dirty[i], = self.db.execute(
                    "UPDATE source SET score=score+? WHERE q='g' AND cid=? RETURNING score",
                    (delta, i)).fetchone()
        return dirty, [num_positive, num_negative, sum(d != 0 for d in net.values()), len(born)]

    def quality(self, targets, anchor):
        if not targets:
            return None
        ids = {self.paths[p] for p in targets if p in self.paths}
        known_anchor = self.paths.get(anchor)
        pool = [i for i in self.degree if i != known_anchor]
        def ranked(score):
            return sorted(pool, key=lambda i: (*score(i), -i), reverse=True)[:K]
        n = self.neighbors.get(known_anchor, {})
        rankings = [ranked(lambda i: (self.degree[i],)), ranked(lambda i: (self.freq[i],)),
                    ranked(lambda i: (self.last[i],)), ranked(lambda i: (n.get(i, 0), self.freq[i]))]
        return [len(targets), len(ids), *[len(ids.intersection(rank)) for rank in rankings]]

def oracle(rows, graph):
    # Direct contribution from a clique of size m is m-1 to each vertex.
    scores = dict.fromkeys(graph.paths, 0)
    for paths in rows:
        for p in paths:
            scores[p] += len(paths)-1
    top = sorted(((graph.paths[p], score) for p, score in scores.items()), key=key, reverse=True)[:K]
    return tuple(top)

def replay(project, rows, window):
    paths = [r[1] if len(r[1]) <= 64 else [] for r in rows]
    db = sqlite3.connect(":memory:")
    db.executescript("""CREATE TABLE source(q TEXT NOT NULL,cid INTEGER NOT NULL,score INTEGER NOT NULL,
        PRIMARY KEY(q,cid)) WITHOUT ROWID;
        CREATE INDEX ix_rank ON source(q,score DESC,cid);""")
    graph = Graph(db)
    controllers = {}
    events = []
    for t, (rev, _) in enumerate(rows):
        if t == WARM:
            for mode in ("classic", "partial"):
                for cap in CAPS:
                    controller = Controller(db, cap, mode)
                    controllers[mode+str(cap)] = controller
            cold = {alg: [int(c.event[k]) for k in COST_FIELDS] for alg,c in controllers.items()}
        general = anchor_case = None
        if t >= WARM and paths[t]:
            general = graph.quality(paths[t], None)
            if len(paths[t]) >= 2:
                anchor = paths[t][int(rev, 16) % len(paths[t])]
                anchor_case = graph.quality([p for p in paths[t] if p != anchor], anchor)
        dirty, counts = graph.apply(paths[t], paths[t-window] if t >= window else [], t)
        ref = oracle(paths[max(0, t-window+1):t+1], graph)
        if t >= WARM:
            costs = []
            for name, c in controllers.items():
                result = c.step(dirty)
                assert result == ref, (project, rev, window, name, result, ref)
                costs.append([c.event["warm_probes"], c.event["warm_rows"]])
            events.append([rev, counts+[int(ref != prev)], costs, general, anchor_case])
        prev = ref
    db.close()
    return {"cold": cold, "events": events, "policies": list(controllers), "path_count": len(graph.paths)}

def main(verify):
    source = read_json(HERE / "commits.json.gz")
    result = {}
    for w in WINDOWS:
        for project, record in source.items():
            print(w, project, flush=True)
            result.setdefault(str(w), {})[project] = replay(project, record["revisions"], w)
    data = {"windows": result, "event_fields": ["rev", "update", "warm_probes_rows_by_policy",
             "unconditional", "conditional"], "update_fields": UPDATE, "quality_fields": QUALITY,
             "cold_fields": COST_FIELDS, "limits": list(CAPS), "sqlite": sqlite3.sqlite_version}
    write_json(HERE / "events.json.gz", data, verify)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    main(parser.parse_args().verify)
