import gzip
import hashlib
import json
import os
from pathlib import Path

D = Path(__file__).resolve().parent
W = D.parents[1]
C = D.parent / "causal_budget"
OFF = W / "graph_memory_round22/native_multiseed/official580"
SEEDS = (13, 17, 29, 37, 41)
ARMS = ("full_rgcn", "wo_chunk_adjacency")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    v = path.read_bytes()
    return json.loads(gzip.decompress(v) if path.suffix == ".gz" else v)


def save(path, obj):
    raw = (json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    tmp = path.with_suffix(path.suffix + ".new")
    tmp.write_bytes(gzip.compress(raw, compresslevel=3, mtime=0) if path.suffix == ".gz" else raw)
    os.replace(tmp, path)


def pack(order, costs, strict):
    packet = []
    left = 2048
    for idx in order:
        if costs[idx] > left:
            if strict:
                break
            continue
        packet.append(idx)
        left -= costs[idx]
    return packet


def panel(trajectories):
    return sorted(trajectories, key=lambda t: hashlib.sha256(("r41-native-prefix-v1|" + t).encode()).digest())[:48]
