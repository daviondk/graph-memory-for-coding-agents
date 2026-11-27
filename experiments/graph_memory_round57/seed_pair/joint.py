"""Two known paths: distinguish pair marginals from candidate-specific joint events."""
from collections import Counter
from fractions import Fraction
from heapq import nlargest
from math import lcm

UNIT = lcm(*range(1, 65))
METHODS = ("sum", "joint", "geometric", "harmonic", "placebo", "joint_first")


def score(selected, events, a, b, recent, fallback):
    pair_a, pair_b, joint = Counter(), Counter(), Counter()
    joint_events = []
    member_count = 0
    for j in selected:
        e = events[j]
        m = len(e)
        member_count += m
        has_a, has_b = a in e, b in e
        assert has_a or has_b
        joint_vote = has_a and has_b and m > 2
        if joint_vote:
            joint_events.append(j)
        for x in e:
            if x == a or x == b:
                continue
            if has_a:
                pair_a[x] += UNIT // (m - 1)
            if has_b:
                pair_b[x] += UNIT // (m - 1)
            if joint_vote:
                joint[x] += UNIT // (m - 2)
    assert sum(joint.values()) == UNIT * len(joint_events)
    pool = set(pair_a) | set(pair_b) | set(fallback)
    pool.difference_update((a, b))
    combined = {x: pair_a[x] + pair_b[x] for x in pool}
    product = {x: pair_a[x] * pair_b[x] for x in pool}
    harmonic = {x: Fraction(2 * product[x], combined[x]) if combined[x] else 0 for x in pool}
    hsum, total = sum(harmonic.values()), sum(combined.values())
    # Every vote for a joint event has unit total mass among its other participants.
    mixture = {x: combined[x] * UNIT + total * joint[x] for x in pool}
    placebo = {x: combined[x] * hsum + total * len(joint_events) * harmonic[x]
               if hsum else combined[x] for x in pool}
    top = {}
    for method, first in (("sum", combined), ("joint", mixture), ("geometric", product),
                          ("harmonic", harmonic), ("placebo", placebo), ("joint_first", joint)):
        ranking = nlargest(8, pool, key=lambda x: (first[x], combined[x], recent[x], -x))
        top[method] = ranking
    if not joint_events:
        assert top["sum"] == top["joint"] == top["placebo"] == top["joint_first"]
    return top, joint_events, member_count
