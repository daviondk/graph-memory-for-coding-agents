"""Choose the history weight on development only; seal all packets before holdout scoring."""
from collections import defaultdict
from fractions import Fraction
from itertools import combinations
from common import *

PACKET_POLICIES = ("current", "min_transfer", "min_length", "min_misses")

def historical(q, state, previous, weight, placebo=False):
    base = state["current"]
    if not previous or weight == 0:
        return base[:8]
    old = {}
    for rank, i in enumerate(previous["current"], 1):
        old.setdefault(previous["keys"][i], rank)
    past = {}
    bands = defaultdict(list)
    for r, i in enumerate(base):
        j = old.get(state["keys"][i])
        if j is not None:
            past[i] = j
            bands[state["seen"][i], r // 8].append(i)
    if placebo:
        for band in bands.values():
            seq = sorted(band, key=lambda i: key(["placebo", q, state["ids"][i]]))
            shift = [past[j] for j in seq[1:] + seq[:1]]
            past.update(zip(seq, shift))
    def order(item):
        r, i = item
        current = r + 1
        before = past.get(i, current)
        exponent = int(4*weight)
        # Four times the log-score is the logarithm of this rational number.
        numerator = current**(4-exponent)
        value = numerator*before**exponent if exponent>=0 else Fraction(numerator,before**(-exponent))
        return state["seen"][i], value, r
    return [i for _, i in sorted(enumerate(base), key=order)[:8]]

def charge(state, indices, cache):
    distinct = {state["keys"][i]:state["tokens"][i] for i in indices}
    return (sum(n for k,n in distinct.items() if k not in cache),
            sum(k not in cache for k in distinct), sum(distinct.values()))

def choose_packet(state, cache, policy, warm):
    base = state["current"]
    k = min(8, len(base))
    if not warm or policy == "current":
        return base[:k]
    seen = sum(state["seen"][i] for i in base[:k])
    ideal = k*(k-1)//2
    best_objective = None
    for pos in combinations(range(min(k+4, len(base))), k):
        loss = sum(pos) - ideal
        if loss > 4:
            continue
        selected = [base[r] for r in pos]
        if sum(state["seen"][i] for i in selected) != seen:
            continue
        traffic, misses, total = charge(state, selected, cache)
        cost = {"min_transfer":traffic, "min_length":total, "min_misses":misses}[policy]
        obj = cost, loss, pos
        if best_objective is None or obj < best_objective:
            best_objective, best = obj, selected
    return best

def main():
    assert sha(HERE/"PROTOCOL_RU.md") == PLAN
    seal = read(HERE/"input-seal.json")
    assert seal["inputs"] == sha(HERE/"inputs.json.gz")
    inputs = read(HERE/"inputs.json.gz")
    dev = {q:z for q,z in inputs.items() if z["panel"] == "dev"}
    dev_path = EXPERIMENTS / "graph_memory_round47/facet_confirmation/ordinal-judgments.json.gz"
    labels = read(dev_path)
    assert labels.keys() == dev.keys()
    totals = []
    for weight in WEIGHTS:
        value = sum(score(historical(q,z,dev.get(z["parent"]),weight),labels[q])[0] for q,z in dev.items())
        totals.append(value)
    best = WEIGHTS[totals.index(max(totals))]
    out = {}
    for q,z in sorted(inputs.items(), key=lambda s:(s[1]["depth"],s[0])):
        p = z["parent"]
        past = inputs.get(p)
        methods = {a:historical(q,z,past,w,placebo) for a,w,placebo in
                   (("calibrated",best,False),("placebo",best,True),("persistence",.5,False),("innovation",-.5,False))}
        for a in PACKET_POLICIES:
            cache = {past["keys"][i] for i in out[p][a]} if p else set()
            methods[a] = choose_packet(z, cache, a, p is not None)
        out[q] = methods
    save("packets.json.gz",out)
    save("forecast-seal.json",dict(inputs=seal["inputs"],protocol=PLAN,temperature=best,weight_grid=WEIGHTS,dev_counts=totals,
         dev_data=sha(dev_path),program=sha(HERE/"predict.py"),common=sha(HERE/"common.py"),packets=sha(HERE/"packets.json.gz")))
    print("Sealed",sum(len(z) for z in out.values()),"packets. Development counts",totals,"chosen λ",best)
if __name__ == "__main__":
    main()

