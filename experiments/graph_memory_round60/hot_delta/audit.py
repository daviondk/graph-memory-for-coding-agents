"""Exercise the hot-complement invariant and a lost-notification counterexample."""
from collections import defaultdict
from contextlib import closing
from random import Random
from tempfile import TemporaryDirectory

from hot_only import HERE, HotOnly, POST, UNCHECKED, EXCEPTION, cold_values, encode_cold
from coverage import Hot, possible_losses, expand
from run_coverage import load, save
from lazy_reader import BlockStore, best
import sys


def run():
    rng = Random(601345)
    checked_slots = rankings = 0
    with TemporaryDirectory(dir=HERE) as root:
        from pathlib import Path
        with closing(BlockStore(Path(root) / "history.sqlite", "filelist", True)) as db:
            hot = Hot()
            policies = [HotOnly(db, hot, size, guard) for size in (64, 256) for guard in (False, True)]
            events = []
            memberships = defaultdict(set)
            for j in range(160):
                files = tuple(sorted({0, *rng.sample(range(1, 19), rng.randrange(1, 6))}))
                losses = possible_losses(hot, files)
                assert db.append(j, f"{j:040x}", files)
                # Seed an empty cold layer after some history exists, as in a real restart.
                events.append(files)
                for f in files:
                    memberships[f].add(j)
                if j == 25:
                    policies = [HotOnly(db, hot, size, guard) for size in (64, 256) for guard in (False, True)]
                if j <= 25:
                    continue
                hot.append(j, files)
                lost = [(k, v) for k, v in losses.items() if k not in hot.live]
                for a in policies:
                    a.after_committed(j, files, lost)
                for f in [0, rng.randrange(19)]:
                    counts = defaultdict(int)
                    for k in memberships[f]:
                        for neighbor in events[k]:
                            counts[neighbor] += 1
                    tie = {x: x % 3 for x in range(19)}
                    prior = sorted(tie, key=lambda x: (-tie[x], x))
                    expect = best(counts, f, tie, prior)
                    for a in policies:
                        observed, _ = a.read(f, tie, prior)
                        assert observed == expect
                        rankings += 1
                        for (tag, x), b in a.cache.items.items():
                            if tag != POST:
                                continue
                            if b[0] in (UNCHECKED, EXCEPTION):
                                h = hot.incident.get(x, set())
                                e = set(cold_values(b))
                                assert not h & e and h | e == memberships[x]
                                checked_slots += 1
                            else:
                                assert set(expand(b)) == memberships[x]
            guarded, trusted = [HotOnly(db, hot, 256, flag) for flag in (True, False)]
            present = {6, 8}  # A lost callback omitted genuinely cold ID 4 from both views.
            x, _ = guarded.recover(encode_cold(4, (2,), True), present)
            y, _ = trusted.recover(encode_cold(4, (2,), False), present)
            assert x is None and y == (2, 6, 8) and set(y) != {2, 4, 6, 8}
    return dict(rank_checks=rankings, disjoint_complements_checked=checked_slots,
                dropped_callback=dict(expected=[2, 4, 6, 8], unchecked=list(y), checked_fallback=x is None))


if __name__ == "__main__":
    outcome = run()
    if "--verify" in sys.argv:
        assert load(HERE / "audit.json") == outcome
    else:
        save(HERE / "audit.json", outcome)
    print(outcome)
