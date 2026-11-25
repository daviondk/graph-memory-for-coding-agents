"""Score fixed strict outputs on the previously published R19 source-overlap partition."""
import sys

from score import ROOT, R19, load, paired, put, sha


EXPECTED_FLAGS = "6568f2d480c8220c3606433b5717b3efc0dfb535e1f58190cacdef458de1d657"


def run(panel):
    flags_path = R19 / "split_overlap/overlap-flags.json.gz"
    assert sha(flags_path) == EXPECTED_FLAGS
    flags = {row["q"]:row for row in load(flags_path)
             if row["train"] == "dense" and row["split"] == "test"}
    results = ROOT / f"{panel}-strict-outcomes.json.gz"
    rows = load(results)
    assert len(flags) == len(rows) == 2000
    assert set(flags) == {row["q"] for row in rows}
    assert all(flags[row["q"]]["t"] == row["t"] for row in rows)
    report = {}
    for name, condition, expected in [("train_field_match", True, 125), ("no_train_field_match", False, 1875)]:
        subset = [r for r in rows if flags[r["q"]]["gold_field"] == condition]
        assert len(subset) == expected
        stat = paired(subset, "F", "skip")
        report[name] = {
            **{k:stat[k] for k in ("n", "tr", "win", "lose")},
            "full_support":stat["change"]["full_support"],
            "coverage":stat["change"]["coverage"],
            "full_support_counts":{arm:int(sum(r["a"][arm]["full_support"] for r in subset))
                                   for arm in ("F", "skip")},
        }
    put(ROOT/f"{panel}-clean-sensitivity.json", {
        "flags_sha256":EXPECTED_FLAGS, "strict_outcomes_sha256":sha(results),
        "train":"Dense-FT; any source field in training",
        "metric":"Does a test field with a reference citation exactly match any training field?",
        "partitions":report,
    })
    print(panel, report["no_train_field_match"])


if __name__ == "__main__":
    run(sys.argv[1])
