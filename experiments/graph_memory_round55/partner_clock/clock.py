"""Prequential file recommendations with lazy endpoint opportunity counters."""
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "graph_memory_round1/git_prediction"))
from run import path_features, jaccard

HALVES = (1, 2, 4, 8, 16, 32, 64, 128)
CLOCKS = ("xor", "anchor", "candidate", "global")
STATIC = ("prior", "unit", "exposure", "jaccard", "ochiai")

def anchor_for(repo, i, observed):
    token = (repo.replace("/", "__") + ":" + str(i)).encode()
    return observed[int.from_bytes(hashlib.sha256(token).digest(), "big") % len(observed)]

@dataclass(slots=True)
class Edge:
    count: int
    unit: float
    exposure: float
    clocks: tuple
    decayed: dict

class Memory:
    def __init__(self, models):
        self.models = tuple(models)
        self.halves = sorted({int(m.split("_")[1]) for m in models if "_" in m})
        self.active = set()
        self.frequency = Counter()
        self.touches = Counter()
        self.edges = defaultdict(dict)

    def times(self, a, b, jointly, index):
        ca, cb = self.touches[a], self.touches[b]
        return ca + cb - 2*jointly, ca, cb, index

    def observe(self, observed, removed, index):
        self.active.difference_update(removed)
        self.active.update(observed)
        self.frequency.update(observed)
        m = len(observed)
        if not 1 <= m <= 20:
            return
        self.touches.update(observed)
        for a in observed:
            for b in observed:
                if a == b:
                    continue
                edge = self.edges[a].get(b)
                count = 1 + (edge.count if edge else 0)
                clocks = self.times(a, b, count, index)
                unit = 1/(m-1)
                decayed = {}
                for k, current in enumerate(clocks):
                    delta = current - edge.clocks[k] if edge else 0
                    assert delta >= 0
                    for h in self.halves:
                        decayed[k,h] = unit + (edge.decayed[k,h]*2**(-delta/h) if edge else 0)
                self.edges[a][b] = Edge(count, unit + (edge.unit if edge else 0),
                                        unit/m + (edge.exposure if edge else 0), clocks, decayed)

    def edge_score(self, model, a, b, edge, index):
        if model == "unit":
            return edge.unit
        if model == "exposure":
            return edge.exposure
        if model == "jaccard":
            return edge.count / (self.touches[a] + self.touches[b] - edge.count)
        if model == "ochiai":
            return edge.count / math.sqrt(self.touches[a] * self.touches[b])
        clock, half = model.split("_")
        k, h = CLOCKS.index(clock), int(half)
        elapsed = self.times(a, b, edge.count, index)[k] - edge.clocks[k]
        return edge.decayed[k,h] * 2**(-elapsed/h)

    def prior(self, a):
        atokens, adirs, astem = path_features(a)
        result = {}
        for b in sorted(self.active - {a}):
            tokens, dirs, stem = path_features(b)
            affinity = 2.5 * bool(astem and astem == stem) + 1.3 * jaccard(atokens, tokens)
            affinity += 0.7 * jaccard(adirs, dirs)
            result[b] = math.exp(affinity) * math.sqrt(self.frequency[b]+1)
        mass = sum(result.values())
        return {b: score / mass for b, score in result.items()}

    def predict(self, a, index):
        prior = self.prior(a)
        known = {b:e for b,e in self.edges.get(a, {}).items() if b in prior}
        total = sum(e.unit for e in known.values())
        ranked = {}
        for model in self.models:
            weights = {} if model == "prior" else {
                b:self.edge_score(model,a,b,e,index) for b,e in known.items()}
            mass = sum(weights.values())
            def order(b):
                # Divide first to preserve ratios even at small total decayed mass.
                graph = (weights.get(b,0.0)/mass)*total if mass else 0.0
                return -(graph+4*prior[b]), -self.frequency[b], b
            ranked[model] = sorted(prior,key=order)[:5]
        return ranked

def evaluate(repo, events, models):
    mem = Memory(models)
    for i,(sha,touched,removed) in enumerate(events):
        if i >= len(events)//2 and 2 <= len(touched) <= 20:
            a = anchor_for(repo,i,touched)
            ranked = mem.predict(a,i)
            targets = [t for t in touched if t != a]
            yield dict(repo=repo,i=i,sha=sha,anchor=a,targets=targets,
                       reachable=len(mem.active.intersection(targets)),ranked=ranked)
        mem.observe(touched,removed,i)
