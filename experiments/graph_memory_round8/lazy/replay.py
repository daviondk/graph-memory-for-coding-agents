"""Causal address forecasts and round-trip checked address transports."""
import gzip
import hashlib
import json
import sys
from extract import ROOT, digest, pack, rows, write_json

NAMES = ["global", "cursor", "first", "nearest", "arbitrary"]
MODES = ["literal", "path", "cursor", "latest", "multi"]


def zig(n):
    return n * 2 if n >= 0 else -2 * n - 1


def unzig(n):
    return n // 2 if not n % 2 else -(n // 2) - 1


def uint(n):
    assert n >= 0
    out = bytearray()
    while n >= 128:
        out.append((n & 127) | 128)
        n >>= 7
    out.append(n)
    return bytes(out)


def read_uint(it):
    value = shift = 0
    while True:
        c = next(it)
        value += (c & 127) << shift
        if c < 128:
            return value
        shift += 7


class Memory:
    def __init__(self, cap):
        self.cap = cap
        self.table = []  # path, up to four search anchors, median of last read
        self.active = None  # coordinate of latest globally active grep: encoded by table index
        self.reference = []  # separate baseline state with at most two positions
        self.base_hot = False
        self.peak = 0

    def serial(self):
        return pack([self.table, self.active])

    def find(self, path):
        return next((i for i, item in enumerate(self.table) if item[0] == path), None)

    def anchors(self):
        return [(p, n) for p, ns, _ in self.table for n in ns]

    def inventory(self):
        # Explicit full address-table contents; an implementation may send shorter deltas.
        return [[p, ns] for p, ns, _ in self.table if ns]

    def advance(self, ev):
        if not ev:
            return
        kind, path, ns = ev
        med = sorted(ns)[(len(ns) - 1) // 2]
        if kind == "search":
            if self.base_hot:
                self.reference.pop()
            self.reference.append([path, ns[0]])
            self.base_hot = True
        else:
            self.reference = [[path, med]]
            self.base_hot = False
        # Sliding single-position reference can drop its never-read fallback if oversized.
        while self.reference and len(pack([self.reference, self.base_hot])) > self.cap:
            self.reference.pop(0)
        self.base_hot = bool(self.reference and self.base_hot)
        ix = self.find(path)
        row = self.table.pop(ix) if ix is not None else [path, [], None]
        self.active = None
        if kind == "search":
            row[1] = list(dict.fromkeys(ns))[:4]
            self.active = 0
        elif kind != "edit":
            row[2] = med
        if kind != "edit":
            self.table.insert(0, row)
        while self.table and len(self.serial()) > self.cap:
            self.table.pop()
        if not self.table:
            self.active = None
        size = len(self.serial())
        assert size <= self.cap
        self.peak = max(self.peak, size)

    def forecast(self, path, iid, t):
        ix = self.find(path)
        _, anchors, cursor = self.table[ix] if ix is not None else (path, [], None)
        first = anchors[0] if anchors else (cursor or 1)
        near = min(anchors, key=lambda n: abs(n - cursor)) if anchors and cursor else first
        toss = int.from_bytes(hashlib.sha256(pack([iid, t, path])).digest()[:4], "big")
        arbitrary = anchors[toss % len(anchors)] if anchors else first
        last = self.reference[-1] if self.reference else None
        return ([last[1] if last and last[0] == path else None, cursor or 1, first, near, arbitrary],
                anchors, ix is not None)

    def codec(self, path, pair):
        lo, hi = pair
        span = hi - lo + 1
        raw = path.encode("utf8")
        options = [b"L" + uint(len(raw)) + raw + uint(lo) + uint(span)]
        ix = self.find(path)
        if ix is not None:
            options.append(b"P" + uint(ix) + uint(lo) + uint(span))
        by_mode = [options[0], min(options, key=len)]
        if ix is not None and self.table[ix][2] is not None:
            options.append(b"C" + uint(ix) + uint(zig(lo - self.table[ix][2])) + uint(span))
        by_mode.append(min(options, key=len))
        if self.active is not None:
            p, anchors, _ = self.table[self.active]
            if p == path:
                options.append(b"G" + uint(zig(lo - anchors[0])) + uint(span))
        by_mode.append(min(options, key=len))
        for slot, (p, n) in enumerate(self.anchors()):
            if p == path:
                options.append(b"A" + uint(slot) + uint(zig(lo - n)) + uint(span))
        by_mode.append(min(options, key=len))
        for word in set(by_mode):
            assert self.decode(word) == (path, lo, hi)
        return [len(s) for s in by_mode], [s[:1].decode() for s in by_mode]

    def decode(self, word):
        it = iter(word)
        typ = chr(next(it))
        if typ == "L":
            p = bytes(next(it) for _ in range(read_uint(it))).decode("utf8")
            lo = read_uint(it)
        elif typ == "P":
            p = self.table[read_uint(it)][0]
            lo = read_uint(it)
        elif typ == "C":
            p, _, cursor = self.table[read_uint(it)]
            lo = cursor + unzig(read_uint(it))
        elif typ == "G":
            p, ns, _ = self.table[self.active]
            lo = ns[0] + unzig(read_uint(it))
        elif typ == "A":
            p, n = self.anchors()[read_uint(it)]
            lo = n + unzig(read_uint(it))
        else:
            raise ValueError(typ)
        span = read_uint(it)
        assert next(it, None) is None
        return p, lo, lo + span - 1


def main():
    inputs = json.loads((ROOT / "inputs.json").read_bytes())
    assert all(digest(ROOT / f) == v for f, v in inputs["files"].items())
    assert [unzig(zig(n)) for n in range(-20000, 20000)] == list(range(-20000, 20000))
    count = 0
    with gzip.GzipFile(str(ROOT / "forecasts.gz"), mode="wb", mtime=0) as out:
        for q in rows(ROOT / "observations.gz"):
            for cap in (512, 128):
                m = Memory(cap)
                change = 0
                changes = 0
                for t, (req, ev) in enumerate(zip(q["requests"], q["events"], strict=True)):
                    if req:
                        path, limits = req
                        pointers, anchors, resident = m.forecast(path, q["id"], t)
                        sizes, codes = m.codec(path, limits) if limits is not None else (None, None)
                        out.write(pack(dict(panel=q["panel"], repo=q["repo"], id=q["id"], cap=cap, t=t,
                                       pointers=pointers, anchors=anchors, sizes=sizes, codes=codes,
                                       resident=resident, state_bytes=len(m.serial()))) + b"\n")
                        count += 1
                    before = m.inventory()
                    m.advance(ev)
                    after = m.inventory()
                    if before != after:
                        change += len(pack(after))
                        changes += 1
                out.write(pack(dict(panel=q["panel"], repo=q["repo"], id=q["id"], cap=cap, t=-1,
                               display_bytes=change, display_changes=changes, peak=m.peak)) + b"\n")
    write_json("lock.json", {"files": {s: digest(ROOT / s) for s in ["inputs.json", "forecasts.gz",
               "PROTOCOL_RU.md", "extract.py", "replay.py", "observations.gz"]}, "forecast_rows": count})


if __name__ == "__main__":
    main()
