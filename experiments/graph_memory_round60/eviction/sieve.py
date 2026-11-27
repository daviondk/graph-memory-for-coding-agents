"""Variable-size FIFO/SIEVE queues for an exact single-writer graph reader."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "coverage"))
from coverage import WithEvictions
from lazy_reader import Cache, EVENT, entry_size, varints


class QueueCache(WithEvictions):
    def __init__(self, quota, policy, notify):
        super().__init__(quota - 2)
        self.quota = quota
        self.policy = policy
        self.notify = notify
        self.visited = set()
        self.hand = None

    def successor(self, key):
        keys = iter(self.items)
        for current in keys:
            if current == key:
                return next(keys, None)
        raise KeyError(key)

    def drop(self, key):
        if self.hand == key:
            self.hand = self.successor(key)
        self.visited.discard(key)
        if self.notify:
            super().drop(key)
        else:
            Cache.drop(self, key)

    def victim(self):
        if self.policy == "fifo":
            return next(iter(self.items))
        while self.items:
            if self.hand is None:
                self.hand = next(iter(self.items))
            if self.hand not in self.visited:
                return self.hand
            self.visited.remove(self.hand)
            self.hand = self.successor(self.hand)
        raise ValueError("empty queue")

    def get(self, key):
        blob = self.items.get(key)
        if blob is not None and self.policy == "sieve":
            self.visited.add(key)
        return blob

    def put(self, key, blob, admission=None, refresh=True):
        charge = entry_size(key, blob)
        old = self.items.get(key)
        if charge > self.limit:
            if old is not None:
                self.drop(key)
            return
        if old is None:
            while self.size + charge > self.limit:
                self.drop(self.victim())
                self.evicted += 1
            self.items[key] = blob
            self.size += charge
        else:
            self.items[key] = blob
            self.size += charge - entry_size(key, old)
            while self.size > self.limit:
                self.drop(self.victim())
                self.evicted += 1
        if key[0] == EVENT and key in self.items:
            self.origin[key[1]] = admission
        self.peak = max(self.peak, self.size)

    def serialized(self):
        keys = list(self.items)
        idx = keys.index(self.hand) + 1 if self.hand is not None else 0
        out = bytearray(idx.to_bytes(2, "little"))
        for key, data in self.items.items():
            out.append(key[0] | (128 if key in self.visited else 0))
            out.extend(varints((key[1] + 1, len(data))))
            out.extend(data)
        assert len(out) == self.size + 2 <= self.quota
        return bytes(out)
