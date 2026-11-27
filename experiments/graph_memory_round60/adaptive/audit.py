"""Evaluate the analytic LRU score against explicit byte-pressure traces."""
from argparse import ArgumentParser
from collections import OrderedDict
from pathlib import Path
from random import Random

from policy import EVENT, POST, XOR, encode, full, projected_value
from lazy_reader import Cache, entry_size, varints
from run_lazy import load, save

HERE = Path(__file__).resolve().parent


def brute(cache, hot, f, ids, packet, self_only):
    cap = cache.limit
    key = (POST, f)
    state = OrderedDict(cache.items)
    state.pop(key, None)
    if entry_size(key, packet) <= cap:
        state[key] = packet
    size = sum(entry_size(k, b) for k, b in state.items())
    value = 0
    # z is abstract admitted bytes newer than every remaining record.
    for z in range(cap):
        while state and size + z > cap:
            victim, blob = state.popitem(last=False)
            size -= entry_size(victim, blob)
        present = {j for (tag, j) in state if tag == EVENT} | hot
        identifiable = packet[0] != XOR or len(set(ids) - present) <= 1
        if key in state and identifiable:
            value += len(varints(ids))
        for (tag, j), b in state.items():
            if tag == EVENT and j not in hot and (not self_only or j in ids):
                value += len(b)
    return value


def audit():
    rng = Random(600714)
    tested = oversize = 0
    for _ in range(480):
        space = rng.choice((4, 8, 16, 25, 64, 100))
        c = Cache(space)
        for what in range(24):
            if rng.randrange(3) == 0:
                c.put((POST, rng.randrange(4)), bytes(rng.randrange(8)))
            else:
                c.put((EVENT, rng.randrange(35)), bytes(rng.randrange(1, 8)))
        items = tuple(sorted(rng.sample(range(35), rng.randrange(26))))
        hot = set(rng.sample(range(35), rng.randrange(22)))
        f = rng.randrange(4)
        packets = [full(items), encode(items, XOR)]
        for blob in packets:
            for local in (False, True):
                expected = brute(c, hot, f, items, blob, local)
                score = projected_value(c, hot, f, set(items), blob, len(varints(items)), local)
                assert score == expected
                tested += 1
                oversize += entry_size((POST, f), blob) > space
    return dict(score_checks=tested, oversized_records=oversize, seed=600714)


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    results = audit()
    if args.verify:
        assert results == load(HERE / "audit.json")
    else:
        save(HERE / "audit.json", results)
    print(results)
