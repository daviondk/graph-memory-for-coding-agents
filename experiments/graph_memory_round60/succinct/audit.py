"""Round-trip complete small universes, random large IDs, and boundary cases."""
from argparse import ArgumentParser
from itertools import combinations
from pathlib import Path
from random import Random
import importlib.metadata
import json

from formats import ENCODERS, Encoder, unpack_list

HERE = Path(__file__).resolve().parent


def check():
    cases = [ids for n in range(11) for ids in combinations(range(10), n)]
    cases += [(0, 127, 128, 16383, 16384, 65535, 65536), tuple(range(500)), (2**31, 2**31+1, 2**32-1)]
    gen = Random(600510)
    for _ in range(256):
        n = gen.randint(1, 96)
        lower = gen.choice((0, 10, 63000, 65510, 2**20))
        cases.append(tuple(sorted(gen.sample(range(lower, lower+gen.randint(n, n*40)), n))))
    for values in cases:
        sizes = []
        for fn in ENCODERS.values():
            blob = fn(values)
            sizes.append(len(blob))
            assert unpack_list(blob) == values
        best = Encoder("best")(values)
        assert len(best) == min(sizes) and unpack_list(best) == values
    return dict(version=importlib.metadata.version("pyroaring"), lists=len(cases), encodes=5*len(cases))


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    result = check()
    dest = HERE / "audit.json"
    if args.verify:
        assert json.loads(dest.read_bytes()) == result
    else:
        dest.write_bytes((json.dumps(result, indent=2) + "\n").encode())
    print(result)
