"""Independent reconstruction of graph visibility from past file windows, without eviction code."""
from collections import Counter, defaultdict
from itertools import chain

from extract import HERE, read, digest


def main():
    for name in ("forecast-seal.json", "invalidation-seal.json", "writeback-seal.json"):
        assert all(digest(HERE / key) == value for key, value in read(HERE / name).items())
    inputs = read(HERE / "prefixes.json.gz")
    forecasts = read(HERE / "forecasts.json.gz")
    group_cache = read(HERE / "writeback-events.json.gz")["16384"]
    src = read(HERE / "sources.json")
    assert len({(s["issue"], s["actor"]) for s in src["sources"]}) == 108
    assert len({s["issue"] for s in src["sources"]}) == 54
    switch_first = Counter()
    queries = 0
    windows = []
    for obs, saved in zip(inputs, forecasts, strict=True):
        q_to_row = {r["at"]: r for r in saved["predictions"]}
        arrivals = {}
        incident = defaultdict(list)
        history = {}
        last = None
        got = set()
        for t, event in enumerate(obs["events"]):
            if len(event) != 3:
                continue
            if event[0] == "open" and last is not None:
                r = q_to_row[t]
                assert r["current"] == last and r["previous_at"] == arrivals[last]
                resident = set(chain.from_iterable(v[-2:] for v in incident.values()))
                own = incident[last][-2:]
                visible = [j for j in incident[last] if j in resident]
                assert [len(own), len(visible), len(incident[last])] == r["cost"]
                assert sorted(set(visible) - set(own)) == r["shared_extra_indices"]
                for method, selected in (("own", own), ("shared", visible), ("full", incident[last])):
                    scores = Counter(b for j in selected for b in history[j] if b != last)
                    order = sorted(arrivals, key=lambda p: (scores[p], arrivals[p]), reverse=True)
                    assert order == r["ranks"][method]
                assert r["target"] == event[1]
                for policy in ("lru", "own", "shared", "full"):
                    tip = next((p for p in r["ranks"][policy] if p != last), last)
                    switch_first[policy] += (tip == event[1])
                got.add(t)
                queries += 1
            path = event[1]
            if last is not None and path != last:
                history[t] = (last, path)
                incident[last].append(t)
                incident[path].append(t)
            arrivals[path] = t
            last = path
        assert got == set(q_to_row)
        windows.extend((saved["issue"], saved["actor"], r) for r in saved["cache"])
    for (iid, actor, row), other in zip(windows, group_cache, strict=True):
        assert (iid, actor, row["at"], row["size"]) == (other["issue"], other["actor"], other["at"], other["bytes"])
        assert row["served"]["graph"] == other["served"]["group_lru"]
        assert all(v <= 16384 for v in row["occupancy"].values())
    print("Most recent alternative file at every open", dict(switch_first))
    print(f"{queries} strictly prior next-open rankings and {len(windows)} cache comparisons verified.")


if __name__ == "__main__":
    main()
