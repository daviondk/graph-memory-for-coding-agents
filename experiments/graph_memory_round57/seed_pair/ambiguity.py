"""Verify indistinguishability of pair-count projections in cyclic triple systems."""
from collections import Counter
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def triples(n, shift):
    return [(a, n + b, 2 * n + (a + b + shift) % n) for a in range(n) for b in range(n)]


def verify(n=16, k=8):
    all_rows = []
    reference = None
    pair_hits = joint_hits = queries = 0
    third_group = set(range(2 * n, 3 * n))
    for shift in range(n):
        rows = triples(n, shift)
        pairs = Counter(pair for event in rows for pair in combinations(event, 2))
        ordered = sorted(pairs.items())
        if reference is None:
            reference = ordered
        assert ordered == reference and len(pairs) == 3 * n * n
        by_seeds = {(a, b): c for a, b, c in rows}
        pair_predictions = sorted(third_group)[:k]
        for a in range(n):
            for b in range(n, 2 * n):
                gold = 2 * n + (a + b - n + shift) % n
                assert by_seeds[a, b] == gold
                pair_hits += gold in pair_predictions
                joint_hits += by_seeds[a, b] == gold
                queries += 1
        all_rows.append(sha256(json.dumps(ordered).encode()).hexdigest())
    assert len(set(all_rows)) == 1
    assert pair_hits * n == k * queries and joint_hits == queries
    return dict(n=n, k=k, worlds=n, events_per_world=n*n, identical_pair_counts=len(reference),
                projection_sha256=all_rows[0], queries=queries, best_possible_pair_hits=pair_hits,
                joint_hits=joint_hits)


if __name__ == "__main__":
    import sys
    result = verify()
    f = HERE / "ambiguity.json"
    if "--verify" in sys.argv:
        assert result == json.loads(f.read_bytes())
    else:
        f.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(result)
