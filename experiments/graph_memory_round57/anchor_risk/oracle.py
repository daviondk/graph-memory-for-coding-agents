"""Exhaustively compare the objective with every permissible top-k decision on small graphs."""
from fractions import Fraction
from itertools import combinations, product
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def solve():
    edges = [(0, 1), (0, 2), (0, 1, 3), (0, 2, 3, 4), (1, 2, 3, 4)]
    vertices = set().union(*edges)
    counter = 0
    strict_reversals = 0
    witness = None
    for masses in product((0, 1, 2, 4), repeat=len(edges)):
        if not any(masses):
            continue
        for a in sorted(vertices):
            candidates = sorted(vertices - {a})
            for k in (1, 2, 3):
                choices = list(combinations(candidates, k))
                optima = []
                for uniform in ("commit", "participation"):
                    direct = dict.fromkeys(choices, 0)
                    pair_score = dict.fromkeys(candidates, 0)
                    for e, mass in zip(edges, masses):
                        if not mass or a not in e:
                            continue
                        m = len(e)
                        # The test generator emits mass/m copies per anchor for commit sampling,
                        # or mass copies per anchor for participation sampling, up to normalization.
                        occurrence = Fraction(mass, m) if uniform == "commit" else Fraction(mass)
                        for answer in choices:
                            direct[answer] += occurrence * Fraction(len(set(e).intersection(answer)), m - 1)
                        divisor = m * (m - 1) if uniform == "commit" else m - 1
                        for b in set(e) - {a}:
                            pair_score[b] += Fraction(mass, divisor)
                    for answer in choices:
                        assert direct[answer] == sum(pair_score[b] for b in answer)
                    best = max(direct.values())
                    rank = sorted(candidates, key=lambda b: (-pair_score[b], b))[:k]
                    assert direct[tuple(sorted(rank))] == best
                    optima.append([list(row) for row in choices if direct[row] == best])
                    counter += 1
                if not {tuple(v) for v in optima[0]}.intersection(map(tuple, optima[1])):
                    strict_reversals += 1
                    if witness is None:
                        witness = dict(edges=edges, mass=masses, anchor=a, k=k, best=optima)
    assert strict_reversals > 0
    return dict(objectives=counter, strict_reversals=strict_reversals, example=witness)


if __name__ == "__main__":
    import sys
    result = json.loads(json.dumps(solve()))
    dest = HERE / "oracle.json"
    if "--verify" in sys.argv:
        assert result == json.loads(dest.read_bytes())
    else:
        dest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(result)
