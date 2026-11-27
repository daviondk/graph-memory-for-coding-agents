"""Maintain a cold posting complement using only changes to the indexed hot graph."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "coverage"))
from coverage import EXCEPTION, POST, SketchPolicy, append_exact, expand, full, pack_exceptions, parts

UNCHECKED = 7


def cold_values(blob):
    if blob[0] == UNCHECKED:
        return expand(blob[1:]) if len(blob) > 1 else ()
    return parts(blob)[1]


def encode_cold(number, cold, checked):
    if checked:
        return pack_exceptions(number, cold)
    return bytes([UNCHECKED]) + (full(tuple(sorted(cold))) if cold else b"")


class HotOnly(SketchPolicy):
    def __init__(self, store, hot, cap, checked):
        super().__init__(store, hot, None, cap)
        self.checked = checked

    def resident(self, f, hot, stats):
        return set(hot)

    def recover(self, record, present):
        cold = cold_values(record)
        ids = present.union(cold)
        if self.checked and len(ids) != parts(record)[0]:
            return None, len(cold)
        return tuple(sorted(ids)), len(cold)

    def admit(self, f, ids, prior, stats):
        exact = full(ids)
        hot = self.hot.incident.get(f, ())
        cold = [j for j in ids if j not in hot]
        short = encode_cold(len(ids), cold, self.checked)
        if len(short) < len(exact):
            stats["stored_complement"] += 1
            return short
        return exact

    def after_committed(self, j, members, losses):
        for file_id in members:
            key = (POST, file_id)
            old = self.cache.items.get(key)
            if old is None or old[0] == UNCHECKED:
                continue
            if old[0] == EXCEPTION:
                number, cold = parts(old)
                new = encode_cold(number + 1, cold, True)
            else:
                new = append_exact(old, j)
            self.cache.put(key, new, refresh=False)
        for dropped, files in losses:
            for file_id in files:
                key = (POST, file_id)
                old = self.cache.items.get(key)
                if old is None or old[0] not in (EXCEPTION, UNCHECKED):
                    continue
                if self.checked:
                    number, cold = parts(old)
                else:
                    number, cold = 0, cold_values(old)
                assert dropped not in cold
                self.cache.put(key, encode_cold(number, (*cold, dropped), self.checked), refresh=False)
