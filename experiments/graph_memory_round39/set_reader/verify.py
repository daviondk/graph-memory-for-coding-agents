"""Check the portable training and prediction seals and the per-state score ledger."""
from pathlib import Path
import gzip
import hashlib
import json

root = Path(__file__).resolve().parent


def load(name):
    value = (root / name).read_bytes()
    if name.endswith(".gz"):
        value = gzip.decompress(value)
    return json.loads(value)


def check(name, digest):
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name


def main():
    manifest = load("manifest.json")["files"]
    for path, digest in manifest.items():
        check(path, digest)

    seal = load("seal.json")
    selection = load("selection.json")
    for path, field in [("selection.json", "selection"), ("predictions.json.gz", "predictions")]:
        check(path, seal[field])
    for path, field in [("PROTOCOL_RU.md", "protocol"), ("fit.py", "fit"), ("data.py", "data_program"), ("trees.json.gz", "trees")]:
        check(path, selection[field])

    summary = load("results.json")
    check("seal.json", summary["seal"])
    check("outcomes.json.gz", summary["outcomes"])
    outcomes = load("outcomes.json.gz")
    predictions = load("predictions.json.gz")
    assert outcomes.keys() == predictions.keys() and len(outcomes) == summary["states"] == 214
    assert len({r["repo"] for r in outcomes.values()}) == summary["repos"] == 69
    for name, scores in summary["arms"].items():
        assert all(len(set(arms[name])) == len(arms[name]) == 8 for arms in predictions.values())
        assert [sum(r["arms"][name][j] for r in outcomes.values()) for j in range(4)] == scores["successes"]
    assert summary["complete_route_checks"] == len(summary["arms"]) * len(outcomes) * 4

    second = load("supervision-seal.json")
    check("supervision.py", second["code"])
    check("SUPERVISION_RU.md", second["protocol"])
    check("supervision-predictions.json.gz", second["forecasts"])
    more = load("supervision-predictions.json.gz")
    more_results = load("supervision-results.json")
    check("supervision-seal.json", more_results["seal"])
    assert more.keys() == outcomes.keys()
    assert all(r["many_distance"] == predictions[q]["matched_unary"] for q, r in more.items())
    assert more_results["successes"]["many_distance"] == summary["arms"]["matched_unary"]["successes"]
    print(f"Verified {len(manifest)} files, {len(outcomes)} states, {len(summary['arms'])} primary arms.")


if __name__ == "__main__":
    main()
