"""Differentially test eviction and in-place resizing with an independent queue model."""
from argparse import ArgumentParser
from random import Random
from sieve import QueueCache, HERE
from lazy_reader import entry_size
from run_coverage import save, load


class Model:
    def __init__(self, quota, scheme):
        self.quota = quota
        self.scheme = scheme
        self.rows = []
        self.cursor = None

    def locate(self, key):
        return next((i for i, row in enumerate(self.rows) if row[0] == key), None)

    def remove(self, i):
        if self.cursor is not None:
            if i < self.cursor:
                self.cursor -= 1
            elif self.cursor == i and i == len(self.rows) - 1:
                self.cursor = None
        self.rows.pop(i)

    def bytes_used(self):
        return 2 + sum(entry_size(k, b) for k, b, _ in self.rows)

    def evict(self):
        if self.scheme == "fifo":
            self.remove(0)
            return
        i = self.cursor if self.cursor is not None else 0
        while self.rows[i][2]:
            self.rows[i][2] = False
            i = (i + 1) % len(self.rows)
        self.cursor = i
        self.remove(i)

    def get(self, key):
        i = self.locate(key)
        if i is None:
            return None
        self.rows[i][2] = self.scheme == "sieve"
        return self.rows[i][1]

    def set(self, key, data):
        i = self.locate(key)
        n = entry_size(key, data)
        if 2 + n > self.quota:
            if i is not None:
                self.remove(i)
            return
        if i is not None:
            self.rows[i][1] = data
            while self.bytes_used() > self.quota:
                self.evict()
        else:
            while self.bytes_used() + n > self.quota:
                self.evict()
            self.rows.append([key, data, False])


def verify():
    gen = Random(60512)
    count = 0
    for scheme in ("fifo", "sieve"):
        for limit in (12, 32, 75, 256):
            oracle = Model(limit, scheme)
            impl = QueueCache(limit, scheme, False)
            for _ in range(2500):
                key = (gen.randrange(2), gen.randrange(13))
                if gen.random() < .4:
                    assert impl.get(key) == oracle.get(key)
                else:
                    blob = bytes([gen.randrange(256)]) * gen.randrange(1, 54)
                    impl.put(key, blob)
                    oracle.set(key, blob)
                assert list(impl.items.items()) == [(k, b) for k, b, _ in oracle.rows]
                assert impl.visited == {k for k, _, flag in oracle.rows if flag}
                expected_hand = oracle.rows[oracle.cursor][0] if oracle.cursor is not None else None
                assert impl.hand == expected_hand
                assert len(impl.serialized()) == oracle.bytes_used()
                count += 1
    return dict(compared_states=count, seed=60512)


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    results = verify()
    if args.verify:
        assert load(HERE / "audit.json") == results
    else:
        save(HERE / "audit.json", results)
    print(results)
