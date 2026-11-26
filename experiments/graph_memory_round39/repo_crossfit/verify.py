"""Audit the portable forecast ledger and all nested repository splits using only the standard library."""
from pathlib import Path
import gzip
import hashlib
import json
from collections import defaultdict

ROOT = Path(__file__).resolve().parent


def read(name):
    data = (ROOT / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def check(name, digest):
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name


def main():
    manifest = read("manifest.json")["files"]
    for name, digest in manifest.items():
        check(name, digest)
    for name, digest in read("seal.json")["local"].items():
        check(name, digest)
    results = read("results.json")
    check("seal.json",results["seal"])
    check("outcomes.json.gz",results["outcomes"])
    pred, outcomes = read("predictions.json.gz"), read("outcomes.json.gz")
    selection = read("selection.json")
    assert len(pred) == 494 and pred.keys() == outcomes.keys()
    group = defaultdict(set)
    for q,row in outcomes.items():
        assert selection["folds"][row["repo"]] == row["fold"]
        group[row["fold"]].add(q)
    assert len(selection["folds"]) == results["repos"] == 171
    for fold in range(5):
        fitted = selection["choices"][str(fold)]
        assert set(fitted["test"]) == group[fold]
        assert set(fitted["dev"]) == group[(fold+1)%5]
        assert set(fitted["train"]) == set(pred)-group[fold]-group[(fold+1)%5]
    methods = results["methods"]
    for name, summary in methods.items():
        outcomes_per_method = [row["metrics"][name] for row in outcomes.values()]
        assert list(map(sum,zip(*outcomes_per_method))) == summary["success"]
        assert all(len(set(arms[name])) == len(arms[name]) == 8 for arms in pred.values())
    print(f"Verified {len(manifest)} files, {len(methods)} arms, 5 disjoint outer folds, 494 states and 171 repositories.")


if __name__ == "__main__":
    main()
