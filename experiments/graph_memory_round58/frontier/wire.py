"""Stateless exact responses for clients with different secondary orders."""
from collections import defaultdict
from itertools import accumulate

METHODS = ("counts", "frontier", "hint", "spec", "shared")
K = 8


def integers(values):
    data = bytearray()
    for x in values:
        if x < 0:
            raise ValueError("negative unsigned field")
        while x >= 128:
            data.append(128 | (x & 127))
            x >>= 7
        data.append(x)
    return bytes(data)


def read_ints(data):
    shift = value = 0
    for x in data:
        value |= (x & 127) << shift
        if x < 128:
            yield value
            value = shift = 0
        else:
            shift += 7
    if shift:
        raise ValueError("truncated varint")


def frame(fields):
    body = integers(fields)
    return integers([len(body)]) + body


def parse(packet):
    size = next(read_ints(packet))
    prefix = integers([size])
    if not packet.startswith(prefix) or len(packet) != size + len(prefix):
        raise ValueError("invalid frame length")
    return list(read_ints(packet[len(prefix):]))


def grouped(counts):
    groups = defaultdict(list)
    for path, value in counts.items():
        if value:
            groups[value].append(path)
    return [(v, sorted(groups[v])) for v in sorted(groups, reverse=True)]


def pack_groups(groups):
    fields = []
    for value, paths in groups:
        previous = -1
        fields.extend((value, len(paths)))
        for path in sorted(paths):
            fields.append(path - previous)
            previous = path
    return fields


def unpack_groups(fields):
    scores = {}
    i = 0
    while i < len(fields):
        value, size = fields[i:i+2]
        i += 2
        deltas = fields[i:i+size]
        if not size or len(deltas) != size or min(deltas) < 1:
            raise ValueError("invalid group")
        for pos in accumulate(deltas):
            if pos - 1 in scores:
                raise ValueError("duplicate path")
            scores[pos - 1] = value
        i += size
    return scores


def ranking(scores, anchor, order, k):
    pool = (i for i in order if i != anchor)
    chosen = sorted(pool, key=lambda i: (-scores.get(i, 0), -order[i], i))[:k]
    return [(i, scores.get(i, 0)) for i in chosen]


def request(method, anchor, order, k=K):
    fields = [METHODS.index(method), anchor + 1]
    if method == "hint":
        fields.extend(i for i, _ in ranking({}, anchor, order, k))
    elif method == "spec":
        fields += [len(order), *pack_groups(grouped(order))]
    return frame(fields)


def serve(packet, get_counts, shared_order=None, k=K):
    opcode, offset, *fields = parse(packet)
    method = METHODS[opcode]
    anchor = offset - 1
    counts = get_counts(anchor)
    if anchor in counts:
        raise ValueError("anchor must be excluded from neighbor scores")
    if method in ("shared", "spec"):
        if method == "spec":
            size, *groups = fields
            scores = unpack_groups(groups)
            order = {i: scores.get(i, 0) for i in range(size)}
        else:
            order = shared_order
            if order is None:
                raise ValueError("order required at the server")
        ranked = ranking(counts, anchor, order, k)
        return frame([1, *(v for pair in ranked for v in pair)])
    groups = []
    remaining = k
    for value, paths in grouped(counts):
        if method != "counts" and remaining <= 0:
            break
        if method == "hint" and len(paths) > remaining:
            at_boundary = set(paths)
            preferred = [p for p in fields if p in at_boundary]
            if len(preferred) >= remaining:
                paths = preferred[:remaining]
        groups.append((value, paths))
        remaining -= len(paths)
    return frame([0, *pack_groups(groups)])


def receive(packet, anchor, order, k=K):
    encoding, *fields = parse(packet)
    if encoding == 1:
        if len(fields) % 2:
            raise ValueError("invalid ranked response")
        return list(zip(fields[::2], fields[1::2]))
    if encoding != 0:
        raise ValueError("unknown response encoding")
    return ranking(unpack_groups(fields), anchor, order, k)
