"""Replay the published and bounded-prefix policies on the packaged 40 signed traces."""
from collections import Counter
from contextlib import closing
import gzip
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parent
if (D / "evidence").is_dir():
    EVIDENCE = D / "evidence"
    CHURN = D / "apps/churn"
    WORK = EVIDENCE / "workload.json.gz"
else:
    EVIDENCE = D.parent
    CHURN = D.parents[1] / "graph_memory_round53/churn"
    WORK = CHURN / "workload.json.gz"
sys.path.insert(0, str(CHURN))
sys.path.insert(0, str(EVIDENCE / "reserve"))

from partial import PartialStore
from classic import ClassicStore
from core import connect


def reference(events):
    views = {}
    for trace, rows in events.items():
        edges = Counter()
        sources = set()
        states = [[]]
        for row in rows:
            sources.update(row["born"])
            for first, second, delta in row["delta"]:
                edges[first, second] += delta
                assert edges[first, second] >= 0
            scores = Counter()
            for (first, _), weight in edges.items():
                scores[first] += weight
            states.append(sorted(((i, scores[i]) for i in sources), key=lambda pair: (-pair[1], pair[0]))[:8])
        views[trace] = states
    return views


def replay(events, expected, implementation, cap):
    counts = Counter()
    with closing(connect(":memory:")) as connection:
        store = implementation(connection, cap)
        for q, rows in events.items():
            for row in rows:
                assert store.update(q, row)
                counts.update(store.event)
        for q, states in expected.items():
            for t, state in enumerate(states):
                for k in (2, 4, 8):
                    assert store.get(q, t, k) == state[:k], (implementation.__name__, cap, q, t, k)
        assert connection.execute("SELECT COUNT(*) FROM packet").fetchone()[0] == 533
    return counts["warm_probes"], counts["warm_rows"], counts["cold_probes"], counts["cold_rows"]


def main():
    events = json.loads(gzip.decompress(WORK.read_bytes()))
    assert len(events) == 40 and sum(map(len, events.values())) == 1072
    states = reference(events)
    expected = {8: ((36, 38), (39, 41)), 9: ((6, 12), (6, 12)), 12: ((0, 0), (0, 0))}
    print("Capacity  plan              warm probes  warm rows  initial probes  initial rows")
    for cap, arms in expected.items():
        for implementation, truth in zip((PartialStore, ClassicStore), arms):
            probes, rows, initial, initial_rows = replay(events, states, implementation, cap)
            assert (probes, rows, initial, initial_rows) == (*truth, 40, 0)
            print(f"{cap:>8}  {implementation.__name__:<16} {probes:>10}  {rows:>9}  {initial:>14}  {initial_rows:>12}")
    print("Verified k=2,4,8 at 1,112 states for six plans against signed-edge reconstruction.")


if __name__ == "__main__":
    main()
