"""Incrementally serve exact graph counts down to the eighth place, including ties."""
from collections import Counter, OrderedDict
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "frontier"))
from wire import frame, grouped, pack_groups, parse, unpack_groups
sys.path.insert(0, str(HERE.parents[1] / "graph_memory_round57" / "block_index"))
from block_store import unpack

MODES = ("flat", "all", "invalidate", "bound8", "bound16")


def cut(scores, width):
    groups = grouped(scores)
    kept = {}
    for score, paths in groups:
        if len(kept) >= width:
            return kept, score
        kept.update((p, score) for p in paths)
    return kept, 0


def advance(known, upper, delta, k=8):
    if upper == 0:
        return Counter(known) + delta, 0
    outside = max((n for path, n in delta.items() if path not in known), default=0)
    upper += outside
    exact = {path: n + delta[path] for path, n in known.items()}
    if sum(n > upper for n in exact.values()) >= k:
        return exact, upper
    return None


class ExactCache:
    def __init__(self, mode, budget):
        self.mode = mode
        self.budget = budget
        self.entries = OrderedDict()
        self.bytes = 0

    def encode(self, packet):
        return packet

    def decode(self, packet):
        return packet

    def put(self, path, offset, upper, scores, meter):
        if self.mode == "flat":
            return
        if self.mode != "all":
            scores, omitted = cut(scores, 16 if self.mode == "bound16" else 8)
            upper = max(upper, omitted)
        packet = self.encode(frame([path+1, offset, upper, *pack_groups(grouped(scores))]))
        charge = len(packet) + 8
        if charge > self.budget:
            meter["oversize"] += 1
            return
        while self.bytes + charge > self.budget:
            _, old = self.entries.popitem(last=False)
            self.bytes -= len(old) + 8
            meter["evictions"] += 1
        self.entries[path] = packet
        self.bytes += charge
        meter["admissions"] += 1

    def read(self, store, path):
        meter = Counter()
        packet = self.entries.pop(path, None)
        offset, upper, known = 0, 0, {}
        if packet is not None:
            self.bytes -= len(packet) + 8
            tag, offset, upper, *groups = parse(self.decode(packet))
            assert tag == path + 1
            known = unpack_groups(groups)
            meter["hits"] += 1

        def events(pointer):
            ids = unpack(pointer)
            bodies, calls = store._fetch_events(ids)
            meter["selects"] += calls
            scores = Counter()
            for (blob,) in bodies:
                scores.update(unpack(blob))
                meter["body"] += len(blob)
            scores.pop(path, None)
            return scores

        suffix = store.db.execute("SELECT substr(js,?) FROM posting WHERE f=?",
                                  (offset + 1,path)).fetchone()
        appended = suffix[0] if suffix else b""
        meter["selects"] += 1
        meter["posting"] += len(appended)
        delta = events(appended)
        state = None
        if packet is None:
            state = delta, 0
        elif not appended:
            state = known, upper
            meter["unchanged"] += 1
        elif self.mode != "invalidate":
            state = advance(known, upper, delta)
            meter["tested"] += 1
            if state is not None:
                meter["certified" if upper else "complete_increment"] += 1
        if state is None:
            meter["refills"] += 1
            if offset:
                previous = store.db.execute("SELECT substr(js,1,?) FROM posting WHERE f=?",
                                            (offset,path)).fetchone()[0]
                assert len(previous) == offset
                meter["selects"] += 1
                meter["posting"] += len(previous)
                delta.update(events(previous))
            state = delta, 0
        scores, upper = state
        self.put(path, offset + len(appended), upper, scores, meter)
        assert self.bytes <= self.budget
        meter["resident"] = self.bytes
        return cut(scores, 8)[0], dict(meter)
