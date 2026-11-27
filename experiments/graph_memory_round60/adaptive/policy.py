"""Estimate the value of a posting representation under an explicit LRU eviction model."""
from pathlib import Path
import sys

R59 = Path(__file__).resolve().parents[2] / "graph_memory_round59"
sys.path.insert(0, str(R59 / "reconcile"))
from summary_cache import EVENT, POST, XOR, SketchPolicy, encode, full, varints
from lazy_reader import entry_size


def lifetime(capacity, newer_including_object):
    return max(0, min(capacity, capacity - newer_including_object + 1))


def projected_value(cache, hot, anchor, ids, packet, posting_bytes, self_only):
    """Sum saved BLOB bytes over all C possible intervening admission volumes."""
    cap = cache.limit
    key = (POST, anchor)
    slot = entry_size(key, packet)
    occupied = slot if slot <= cap else 0
    posting_survival = lifetime(cap, slot)
    bodies = {}
    value = 0
    for address, blob in reversed(cache.items.items()):
        if address == key:
            continue
        occupied += entry_size(address, blob)
        life = lifetime(cap, occupied)
        if life == 0:
            break
        kind, event = address
        if kind == EVENT and event not in hot:
            if event in ids:
                bodies[event] = life
            if not self_only or event in ids:
                value += len(blob) * life
    if packet[0] == XOR and len(ids) >= 2:
        # The second eviction makes an XOR posting unusable at this anchor.
        shortest = second = cap
        for event in ids:
            life = cap if event in hot else bodies.get(event, 0)
            if life <= shortest:
                shortest, second = life, shortest
            elif life < second:
                second = life
        posting_survival = min(posting_survival, second)
    return value + posting_bytes * posting_survival


class Adaptive(SketchPolicy):
    def __init__(self, store, hot, cap, self_only=False):
        super().__init__(store, hot, XOR, cap)
        self.self_only = self_only

    def admit(self, f, ids, record, stats):
        exact = full(ids)
        short = encode(ids, XOR)
        if short[0] != XOR:
            stats["same_representation"] += 1
            return exact
        args = (self.cache, self.hot.live, f, set(ids))
        width = len(varints(ids))
        exact_value = projected_value(*args, exact, width, self.self_only)
        short_value = projected_value(*args, short, width, self.self_only)
        if short_value > exact_value:
            stats["selected_xor"] += 1
            return short
        stats["selected_full"] += 1
        return exact
