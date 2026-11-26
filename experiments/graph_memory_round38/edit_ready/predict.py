"""Freeze all-path, pre-action cache contents using public observations only."""
from collections import deque
from common import D, get, save, sha


POLICIES = ("tail", "head", "center", "grid", "focus")
BUDGETS = ("16", "64", "128", "2048B")
METHODS = ["full"] + [f"{p}-{b}" for p in POLICIES for b in BUDGETS]


def order(rows, policy, previous, path):
    numbers = [r[0] for r in rows]
    if policy == "head":
        return rows
    if policy == "tail":
        return rows[::-1]
    low, high = numbers[0], numbers[-1]
    if policy in ("center", "focus"):
        if policy == "focus" and previous and previous[0] == path:
            left, right = max(low, previous[1]), min(high, previous[2])
            if left <= right:
                low, high = left, right
        return sorted(rows, key=lambda r: (abs(2 * r[0] - low - high), r[0]))
    # Divide the coordinate interval breadth-first. Missing rows carry no facts.
    sections = deque([(numbers[0], numbers[-1])])
    lookup = {r[0]: r for r in rows}
    ranked = []
    while sections:
        left, right = sections.popleft()
        midpoint = (left + right) // 2
        if midpoint in lookup:
            ranked.append(lookup[midpoint])
        if left < midpoint:
            sections.append((left, midpoint - 1))
        if midpoint < right:
            sections.append((midpoint + 1, right))
    return ranked


class Cache:
    def __init__(self, budget):
        self.budget = budget
        self.facts = {}

    def invalidate(self, path):
        self.facts = {k: f for k, f in self.facts.items() if k[0] != path}

    def observe(self, path, ranked):
        old, kept = self.facts, {}
        limit = 2048 if self.budget == "2048B" else int(self.budget or 10**18)
        remaining = limit
        for number, digest, size, eol, reference in ranked:
            key = path, number
            previous = old.pop(key, None)
            # Repeated identical observations may preserve an earlier LF witness.
            if previous and previous[1] == digest and previous[3] and not eol:
                fact = previous
            else:
                fact = (number, digest, size, eol, reference)
            cost = 13 + size if self.budget == "2048B" else 1
            if cost <= remaining:
                kept[key] = fact
                remaining -= cost
        for key, fact in old.items():
            cost = 13 + fact[2] if self.budget == "2048B" else 1
            if cost <= remaining:
                kept[key] = fact
                remaining -= cost
        self.facts = kept

    def snapshot(self):
        return [f[4] for f in self.facts.values()]


def replay(events, visible):
    full = Cache(None)
    bounded = {p: [Cache(b) for b in BUDGETS] for p in POLICIES}
    caches = [full] + [c for p in POLICIES for c in bounded[p]]
    snapshots, previous, next_ref = {}, None, 0
    for event in events:
        at, kind = event[:2]
        if kind == "reset":
            for c in caches:
                c.facts.clear()
            previous = None
        elif kind == "view":
            path = event[2]
            rows = [(*row, next_ref + j) for j, row in enumerate(visible[str(at)])]
            next_ref += len(rows)
            assert rows and all(a[0] < b[0] for a, b in zip(rows, rows[1:]))
            full.observe(path, rows)
            for p in POLICIES:
                ranked = order(rows, p, previous, path)
                for c in bounded[p]:
                    c.observe(path, ranked)
            previous = (path, rows[0][0], rows[-1][0])
        else:
            # Snapshot has no action arguments. Only then consume the invalidated path.
            if kind == "snapshot+invalidate":
                snapshots[at] = [c.snapshot() for c in caches]
            else:
                assert kind == "invalidate"
            for c in caches:
                c.invalidate(event[2])
    return snapshots


def main():
    inputs = get(D / "input-seal.json")
    for name in ("schedule.json.gz", "visible.json.gz"):
        assert sha(D / name) == inputs["artifacts"][name]
    assert sha(D / "PROTOCOL_RU.md") == inputs["frozen_protocol"]
    timeline, views = [get(D / n) for n in ("schedule.json.gz", "visible.json.gz")]
    predictions = {r: replay(m["events"], views[r]) for r, m in timeline.items()}
    path = D / "predictions.json.gz"
    pred = save(path, {"methods": METHODS, "snapshots": predictions})
    save(D / "prediction-seal.json", {
        "inputs": sha(D / "input-seal.json"), "protocol": inputs["frozen_protocol"],
        "implementation": sha(D / "predict.py"), "common": sha(D / "common.py"),
        "implementation_notes": sha(D / "IMPLEMENTATION_RU.md"),
        "predictions": pred, "snapshots": sum(map(len, predictions.values())),
        "methods": METHODS, "runs": len(predictions),
    })
    print("Frozen", pred)


if __name__ == "__main__":
    main()
