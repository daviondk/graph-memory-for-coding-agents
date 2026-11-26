"""Offline replay of measurements, source-span judgements and an independent exact selection."""
from collections import Counter, defaultdict
from hashlib import sha256
import gzip
import json
from math import isclose
from pathlib import Path
from statistics import median

D = Path(__file__).resolve().parent

def get(name):
    raw = (D / name).read_bytes()
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)

def sha(name):
    return sha256((D / name).read_bytes()).hexdigest()

def reference(cols, events, step, cap):
    # Independent integer subset DP. The selected mask also implements the order at a utility tie.
    visible = [r for r in cols if r[0] <= step]
    balance = dict(pair for group in events[:step] for pair in group)
    head = []
    left = 2048
    for row in reversed(visible):
        if left - row[2] < 1024:
            break
        head.append(row[1])
        left -= row[2]
    opt = visible[:len(visible) - len(head)]
    best = [(0, 0)] * (left + 1)
    for index, (_, _, price, value, owners) in enumerate(opt):
        weight = value + sum(min(cap, balance.get(src, 0)) << 28 for src in owners)
        bit = 1 << index
        for w in range(left, price - 1, -1):
            u, mask = best[w - price]
            if u + weight > best[w][0]:
                best[w] = u + weight, mask | bit
    mask = best[left][1]
    return head + [r[1] for j, r in reversed(list(enumerate(opt))) if mask >> j & 1]

def main():
    inp, packets, judgments, scores, results = map(get, ("input.json.gz", "packets.json.gz",
        "judgments.json.gz", "scores.json.gz", "results.json"))
    seal = get("forecast-seal.json")
    assert sha("stream.cpp") == seal["code"] and sha("packets.json.gz") == seal["packets"]
    assert sha("input.json.gz") == seal["inputs"] and sha("timing.json.gz") == seal["times"]
    assert sha("judgments.json.gz") == get("judgment-source.json")["file"]
    assert sha("forecast-seal.json") == get("judgment-source.json")["forecast_seal"]
    assert set(inp) == set(packets) == set(judgments) == set(scores)
    assert len(inp) == 2000 and len({v[0] for v in inp.values()}) == 1207
    assert sum(len(v[2]) for v in inp.values()) == 51849
    times = defaultdict(list)
    counters = {}
    for q, repeat, mode, period, ns, visits, rewound, peak in get("timing.json.gz"):
        key = q, mode, period
        times[key].append((repeat, ns))
        assert counters.setdefault(key, (visits, rewound, peak)) == (visits, rewound, peak)
    for mode, period in seal["modes"]:
        total = 0
        peaks = []
        rows = rewinds = 0
        for q in inp:
            key = q, mode, period
            observations = sorted(times[key])
            assert [i for i,_ in observations] == [1,2,3,4,5]
            total += median([ns for _,ns in observations])
            v, r, peak = counters[key]
            rows += v
            rewinds += r
            peaks.append(peak)
        measured = results["time"][f"{mode}/{period}"]
        assert measured["cpu_ms"] == total/1e6 and measured["dp_rows"] == rows
        assert measured["rewound"] == rewinds and measured["max_dp_bytes"] == max(peaks)
        assert measured["median_peak_bytes"] == median(peaks)
    agg = defaultdict(list)
    checks = 0
    sample = set(sorted(inp, key=lambda q: sha256(("independent-r49/"+q).encode()).digest())[:32])
    for q, (_, cols, ev) in inp.items():
        units = {r[1]:r for r in cols}
        marks = judgments[q]
        for stage, sv in scores[q].items():
            step = len(ev) if stage == "final" else 8
            assert sv[0] == all(any(units[i][0] <= step for i in ids) for w,ids in marks)
            for policy, order in packets[q][str(step)].items():
                selected = set(order)
                assert len(order) == len(selected) and all(units[i][0] <= step for i in selected)
                cost = sum(units[i][2] for i in selected)
                assert cost <= 2048
                total = sum(w for w, _ in marks)
                covered = sum(w for w, ids in marks if selected.intersection(ids))
                score = [int(total == covered), covered/total, cost]
                assert score == sv[1][policy]
                for group in (["all_fired","available"] if sv[0] else ["all_fired"]):
                    agg[stage, group, policy].append(score)
                if q in sample and policy != "dense":
                    assert reference(cols, ev, step, 4 if policy == "full" else 0) == order
                    checks += 1
    for (stage,group,policy), rows in agg.items():
        result = results["quality"][f"{stage}/{group}"]
        assert result["n"] == len(rows)
        means = [sum(row[i] for row in rows) / len(rows) for i in range(3)]
        assert all(isclose(result["methods"][policy][metric], v, abs_tol=1e-12)
                   for metric, v in zip(("full","coverage","tokens"), means))
    print(f"Verified {len(inp)} questions, {len(times)*5} timed trials and {checks} independent exact packets.")
if __name__ == "__main__":
    main()
