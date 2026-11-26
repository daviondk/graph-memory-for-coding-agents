"""Descriptive relevance stratification; run after predictions have been frozen."""
from collections import Counter, defaultdict

from inputs import HERE, R54, read, save


def main():
    obs = read(HERE/"observations.json.gz")
    panel = read(R54/"learned_read/projection.json.gz")
    labels = read(R54/"next_read/labels.json.gz")
    rows = defaultdict(Counter)
    for q, t in obs.items():
        if len(t["proposals"]) < 2:
            continue
        last = set(t["proposals"][-1])
        earlier = {p for seq in t["proposals"][:-1] for p in seq}
        relevant = set(labels[q])
        for p in panel[q]["paths"]:
            state = ("repeated" if p in earlier else "new_last") if p in last else ("withdrawn" if p in earlier else "never")
            rows[state]["pairs"] += 1
            rows[state]["relevant"] += int(p in relevant)
    result = {state: dict(counts) for state, counts in sorted(rows.items())}
    save("proposal-audit.json", result)
    print(result)


if __name__ == "__main__":
    main()
