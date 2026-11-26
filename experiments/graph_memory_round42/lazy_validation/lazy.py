"""Exact late validation for a protected prefix followed by a stable additive optimum."""

def first_risk(rows, chosen, unknown, threshold):
    """Find a witness that some completion could make an unselected item mandatory."""
    fixed_cost = 0
    first_unknown = None
    for candidate, _, cost, _ in rows:
        if candidate in unknown and first_unknown is None:
            first_unknown = candidate
        # Keep the candidate itself and remove all unknown predecessors.
        if candidate not in chosen and fixed_cost + cost <= threshold:
            if first_unknown is None:
                raise AssertionError("A known prefix unit is missing from the optimistic packet")
            return first_unknown
        if candidate not in unknown:
            fixed_cost += cost
            if fixed_cost > threshold:
                break
    return None


def materialize(rows, unresolved, lookup, select, threshold, exact=True):
    """Return selected IDs and list of probes. Resolved addresses remain in the caller's store."""
    unknown = set(unresolved)
    active = list(rows)
    queried = []
    packs = 0
    while True:
        packet, _, boundary = select(active)
        packs += 1
        probes = [i for i in packet if i in unknown]
        if not probes:
            if exact:
                risk = first_risk(active, set(packet), unknown, threshold)
            else:
                risk = boundary if boundary in unknown else None
            if risk is None:
                return list(packet), queried, packs
            probes = [risk]
        missing = set()
        for i in probes:
            if not lookup(i):
                missing.add(i)
            unknown.remove(i)
        queried.extend(probes)
        if missing:
            active = [r for r in active if r[0] not in missing]

