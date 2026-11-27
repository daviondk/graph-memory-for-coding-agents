"""Small, independently decodable full postings and native portable Roaring serialization."""
from collections import Counter
from pathlib import Path
import sys

R59 = Path(__file__).resolve().parents[2] / "graph_memory_round59"
sys.path.insert(0, str(R59 / "reconcile"))
from summary_cache import full as basic, expand as expand_basic, varints

from pyroaring import BitMap

EF = 8
BIC = 9
ROAR = 10


def number(data, pos):
    v = 0
    shift = 0
    while True:
        c = data[pos]
        pos += 1
        v |= (c & 127) << shift
        if c < 128:
            return v, pos
        shift += 7


def elias_fano(ids):
    if not ids:
        return bytes((EF, 0))
    n = len(ids)
    low_width = max(0, ((ids[-1] + 1) // n).bit_length() - 1)
    mask = (1 << low_width) - 1
    lows = sum((x & mask) << (i * low_width) for i, x in enumerate(ids))
    high = sum(1 << ((x >> low_width) + i) for i, x in enumerate(ids))
    return (bytes([EF]) + varints((n, low_width))
            + lows.to_bytes((n * low_width + 7) // 8, "little")
            + high.to_bytes((high.bit_length() + 7) // 8, "little"))


def ef_values(blob):
    n, p = number(blob, 1)
    if n == 0:
        return ()
    low_width, p = number(blob, p)
    nb = (n * low_width + 7) // 8
    low = int.from_bytes(blob[p:p + nb], "little")
    high = int.from_bytes(blob[p + nb:], "little")
    mask = (1 << low_width) - 1
    ids = []
    for i in range(n):
        pos = (high & -high).bit_length() - 1
        ids.append(((pos - i) << low_width) | ((low >> (low_width * i)) & mask))
        high &= high - 1
    assert not high
    return tuple(ids)


class Bits:
    def __init__(self, blob=b""):
        self.value = int.from_bytes(blob, "big")
        self.length = 8 * len(blob)

    def put(self, x, n):
        self.value = (self.value << n) | x
        self.length += n

    def take(self, n):
        self.length -= n
        assert self.length >= 0
        return (self.value >> self.length) & ((1 << n) - 1)

    def bytes(self):
        return (self.value << (-self.length % 8)).to_bytes((self.length + 7) // 8, "big")


def bic_tree(values, start, stop, low, high, stream, decode):
    if start >= stop:
        return
    mid = (start + stop) // 2
    lo = low + mid - start
    hi = high - (stop - mid - 1)
    span = hi - lo + 1
    width = span.bit_length() - 1
    short = (1 << (width + 1)) - span
    if decode:
        val = stream.take(width)
        if val >= short:
            val = (val << 1) + stream.take(1) - short
        values[mid] = lo + val
    else:
        val = values[mid] - lo
        if val < short:
            stream.put(val, width)
        else:
            stream.put(val + short, width + 1)
    bic_tree(values, start, mid, low, values[mid] - 1, stream, decode)
    bic_tree(values, mid + 1, stop, values[mid] + 1, high, stream, decode)


def interpolative(ids):
    out = bytes([BIC]) + varints((len(ids),))
    if not ids:
        return out
    stream = Bits()
    bic_tree(ids, 0, len(ids) - 1, 0, ids[-1] - 1, stream, False)
    return out + varints((ids[-1],)) + stream.bytes()


def bic_values(blob):
    n, p = number(blob, 1)
    if not n:
        return ()
    last, p = number(blob, p)
    out = [0] * n
    out[-1] = last
    bic_tree(out, 0, n - 1, 0, last - 1, Bits(blob[p:]), True)
    return tuple(out)


def roaring(ids):
    bitmap = BitMap(ids)
    bitmap.run_optimize()
    return bytes([ROAR]) + bitmap.serialize()


def unpack_list(blob):
    tag = blob[0]
    if tag == EF:
        return ef_values(blob)
    if tag == BIC:
        return bic_values(blob)
    if tag == ROAR:
        return tuple(BitMap.deserialize(blob[1:]))
    return expand_basic(blob)


ENCODERS = {"basic": basic, "ef": elias_fano, "bic": interpolative, "roaring": roaring}


class Encoder:
    def __init__(self, mode):
        self.encode = ENCODERS.values() if mode == "best" else (ENCODERS[mode],)
        self.selected = Counter()

    def __call__(self, ids):
        blob = min((fn(ids) for fn in self.encode), key=len)
        self.selected[blob[0]] += 1
        return blob
