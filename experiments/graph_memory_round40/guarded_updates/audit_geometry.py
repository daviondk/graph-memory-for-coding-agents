"""Recover true replacement coordinates independently from raw request and receipt."""
from collections import Counter
from shared import D, read, save, sha, raw_events


def main():
    selections = read(D / "selections.json.gz")
    assert sha(D / "selections.json.gz") == read(D / "selection-seal.json")["selection"]
    rows = [dict(rid=r["run"], view=r["view"], event=r["at"], receipt=r["receipt"]) for r in selections]
    raw = raw_events(rows)
    counts = Counter()
    diffs = []
    for r in selections:
        events = raw[r["run"]]
        act = events[r["at"]]["action"]
        obs = events[r["receipt"]]["observation"]
        old = act["old_str"]
        pre = obs["old_content"]
        offset = pre.index(old)
        assert pre.count(old) == 1 and pre.replace(old, act["new_str"], 1) == obs["new_content"]
        start = 1 + pre.count("\n", 0, offset)
        end = start + old.count("\n")
        delta = act["new_str"].count("\n") - old.count("\n")
        expected = (r["start"], r["end"], r["delta"])
        actual = (start, end, delta)
        counts["receipts"] += 1
        counts["geometry_exact"] += int(expected == actual)
        if expected != actual:
            diffs.append([r["run"], r["at"], *expected, *actual])
    save(D / "geometry-check.json", dict(counts=counts, differences=diffs, selection=sha(D / "selection-seal.json")))
    print(dict(counts))


if __name__ == "__main__":
    main()
