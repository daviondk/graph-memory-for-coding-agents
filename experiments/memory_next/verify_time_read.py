"""Reconstruct the decision ledger from dates, blind rankings, raw answers and released relations."""
import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TIME = ROOT / "time_read"


def load(path):
    return json.loads(path.read_text(encoding="utf8"))


def table(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    for name, digest in load(TIME / "end_lock.json").items():
        assert hashlib.sha256((TIME / name).read_bytes()).hexdigest() == digest, name
    costs = load(TIME / "results.json")
    raw = [json.loads(s) for s in (TIME / "calls.jsonl").read_text(encoding="utf8").splitlines()]
    by_hash = {r["payload_sha256"]: r for r in raw}
    assert len(raw) == len(by_hash) == costs["costs"]["actual_calls"]
    assert sum(r["usage"]["prompt_tokens"] for r in raw) == costs["costs"]["input"]
    assert sum(r["usage"]["completion_tokens"] for r in raw) == costs["costs"]["output"]
    preds = {(r["ordinal"], r["arm"]): r for r in load(TIME / "blind_decisions.json")}
    assert len(preds) == 198
    clocks = table(ROOT / "transfer" / "query_times_lite.csv")
    sources = {r["trace_key"]: r for r in table(ROOT / "transfer" / "source_times_lite.csv")}
    links = table(ROOT / "transfer" / "lite_chronology.csv")
    results = table(TIME / "per_query.csv")
    for sl, r, t, l in zip(load(TIME / "blind_lists.json"), results, clocks, links, strict=True):
        i = int(r["ordinal"])
        assert int(t["ordinal"]) == int(l["ordinal"]) == sl["ordinal"] == i
        assert r["id"] == t["target"] == l["target"]
        eligible = {k for k, s in sources.items()
                    if t["opening_complete"] == "1" and s["repo"].lower() == t["repo"].lower()
                    and s["source_pr"] != t["target_pr"] and s["source_merge"]
                    and stamp(s["source_merge"]) < stamp(t["cutoff_utc"])}
        assert sorted(eligible) == sl["eligible"] and len(eligible) == int(r["pool"])
        gold = l["gold"].split("|")
        linked = {k for k in eligible if sources[k]["instance_id"] in gold}
        assert len(linked) == int(r["linked"])
        for arm, ranks in sl["ranks"].items():
            assert len(ranks) == len(eligible) and set(ranks) == eligible
            for k in (1, 5):
                assert bool(linked.intersection(ranks[:k])) == int(r[f"{arm}_{k}"])
        for arm in ("hyb_real", "online_fields"):
            a = preds[(i, arm)]
            top = sl["ranks"][arm][:5]
            choice = next(iter(top), None)
            if len(top) > 1:
                call = by_hash[a["payload_sha256"]]
                assert set(call["order"]) == set(top) and len(call["order"]) == len(top)
                match = re.fullmatch(r"\s*([1-5])[.)]?\s*", call["raw"] or "")
                valid = bool(match and int(match[1]) <= len(top))
                assert a["valid"] == valid
                if valid:
                    choice = call["order"][int(match[1]) - 1]
            else:
                assert a["payload_sha256"] is None
            assert choice == a["choice"]
            assert int(r[arm + "_qwen"]) == (choice in linked)
            assert int(r[arm + "_qwen_last"]) == (choice is not None and sources[choice]["instance_id"] == gold[-1])
    assert len(results) == len(clocks) == len(links) == 99
    assert costs["costs"]["empty"] == sum(int(r["pool"]) == 0 for r in results)
    assert costs["costs"]["singleton"] == sum(int(r["pool"]) == 1 for r in results)
    for name, min_pool, need_gold in (("all",0,False), ("label_available",0,True),
                                      ("available_competing",2,True), ("available_5plus",5,True)):
        rows = [r for r in results if int(r["pool"]) >= min_pool and (not need_gold or int(r["linked"]) > 0)]
        out = costs[name]
        assert len(rows) == out["n"] and len({r["repo"] for r in rows}) == out["repos"]
        assert len({(r["repo"], r["pr"]) for r in rows}) == out["distinct_pr"]
        assert all(sum(int(r[k]) for r in rows) == v for k, v in out["hits"].items())
        assert abs(sum(float(r["chance"]) for r in rows) - out["chance_expected_hits"]) < 1e-9
    print(f"Verified 99 historical candidate pools, 198 assignments and {len(raw)} real reader calls.")


if __name__ == "__main__":
    main()

