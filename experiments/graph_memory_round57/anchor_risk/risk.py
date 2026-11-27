"""Rank prior co-change events under different sampling and utility assumptions."""
from collections import Counter, defaultdict, deque
from heapq import nlargest
from math import lcm

WEIGHTS = ("count", "companion", "commit", "heavy")
SCALE = lcm(*range(1, 65)) ** 3
WEIGHT = {m: (1, SCALE // (m - 1), SCALE // (m * (m - 1)),
              SCALE // (m * m * (m - 1))) for m in range(2, 65)}


class History:
    def __init__(self):
        self.ids = {}
        self.frequency = Counter()
        self.window = deque(maxlen=32)
        self.events = []
        self.post = defaultdict(list)
        self.tail = defaultdict(deque)
        self.owners = Counter()
        self.hot = defaultdict(set)

    def observe(self, paths):
        ids = tuple(self.ids.setdefault(p, len(self.ids)) for p in paths)
        if len(self.window) == self.window.maxlen:
            self.frequency.subtract(self.window[0])
        self.window.append(ids)
        self.frequency.update(ids)
        if len(ids) < 2:
            return
        j = len(self.events)
        self.events.append(ids)
        for f in ids:
            self.post[f].append(j)
            self.hot[f].add(j)
            tail = self.tail[f]
            if len(tail) == 8:
                old = tail.popleft()
                self.owners[old] -= 1
                if not self.owners[old]:
                    del self.owners[old]
                    for member in self.events[old]:
                        self.hot[member].remove(old)
            tail.append(j)
            self.owners[j] += 1

    def select(self, anchor):
        recent = sorted(self.hot.get(anchor, ()), reverse=True)
        short = [j for j in recent if len(self.events[j]) <= 6]
        fill = short[:8]
        if len(fill) < 8:
            fill += [j for j in recent if len(self.events[j]) > 6][:8-len(fill)]
        return {"fill6": fill, "own": self.tail.get(anchor, ()), "full": self.post.get(anchor, ())}

    def rank(self, anchor, events, fallback):
        counts = {}
        members = 0
        for j in events:
            ids = self.events[j]
            weight = WEIGHT[len(ids)]
            members += len(ids)
            for i in ids:
                if i == anchor:
                    continue
                if i not in counts:
                    counts[i] = list(weight)
                else:
                    totals = counts[i]
                    for v in range(4):
                        totals[v] += weight[v]
        for i in fallback:
            if i != anchor and i not in counts:
                counts[i] = [0] * 4
        ranks = []
        for v in range(4):
            top = nlargest(8, counts, key=lambda i: (counts[i][v], self.frequency[i], -i))
            ranks.append(top)
        return ranks, members

    def query(self, anchor, fallback):
        ranks = []
        modes = {}
        seen = {}
        for reader, selected in self.select(anchor).items():
            key = tuple(sorted(selected))
            if key not in seen:
                output, members = self.rank(anchor, key, fallback)
                indices = []
                for row in output:
                    if row not in ranks:
                        ranks.append(row)
                    indices.append(ranks.index(row))
                seen[key] = [len(key), members, indices]
            modes[reader] = seen[key]
        return {"packets": ranks, "readers": modes}


def replay(stream, eligible):
    state = History()
    output = []
    for t, (sha, changed) in enumerate(stream):
        paths = changed if len(changed) <= 64 else []
        if len(paths) >= 2 and eligible(t, sha):
            prior_ids = [state.ids.get(p, -1) for p in paths]
            fallback = nlargest(9, range(len(state.ids)), key=lambda i: (state.frequency[i], -i))
            by_anchor = {}
            for a in dict.fromkeys(prior_ids):
                by_anchor[a] = state.query(a, fallback)
            # Unknown paths have the same empty history but retain separate evaluation weight.
            output.append({"sha": sha, "t": t, "ids": prior_ids,
                           "answers": {str(a): value for a, value in by_anchor.items()}})
        state.observe(paths)
    return output
