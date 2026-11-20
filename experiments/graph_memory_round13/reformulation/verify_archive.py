"""Verify all sealed files; reproduce rankings and primary scores from this archive alone."""
import gzip
import json
from pathlib import Path
import rank

ROOT = Path(__file__).resolve().parent

def main(panel):
    rank.D = panel
    seals = rank.load("forecast.lock.json")["files"]
    for name, digest in seals.items():
        assert rank.h((panel / name).read_bytes()) == digest, name
    rows = rank.load("inputs.json.gz")
    nav = {v["id"]: v["target"] for v in rank.load("navigation_labels.json.gz")}
    diffs = {v["iid"]: v for v in rank.load("patch_labels.json.gz")}
    predicted = {v["id"]: v["rank"] for v in rank.load("frozen_rankings.json.gz")}
    expected = rank.load("results.json")["endpoints"]
    counters = {}
    for r in rows:
        submitted = predicted[r["id"]]
        repeated, _ = rank.calculate(r)
        assert repeated == submitted, r["id"]
        labels = {}
        if nav[r["id"]]:
            labels["next"] = {nav[r["id"]]["path"]}
        pr = diffs[r["iid"]]
        if pr.get("strict") and pr["prod"]:
            labels["patch"] = set(pr["prod"])
        for end, targets in labels.items():
            for method, files in repeated.items():
                successes = counters.setdefault((end,method),[])
                successes.append(next((i+1 for i,f in enumerate(files) if f in targets),0))
    for (end, method), ranks in counters.items():
        official = expected[end]["all"]
        score = official["score"][method]
        assert len(ranks) == official["n"] and ranks.count(1) == score["h1"]
        assert sum(0<r<=3 for r in ranks) == score["h3"]
        assert abs(sum(1/r for r in ranks if r)/len(ranks) - score["mrr"]) < 1e-12
    print(panel.name, len(rows), "all forecasts and both primary endpoints verified")

if __name__ == "__main__":
    manifest = json.loads((ROOT / "MANIFEST_SHA256.json").read_bytes())
    for name, digest in manifest.items():
        assert rank.h((ROOT / name).read_bytes()) == digest, name
    for p in (ROOT,ROOT/"replication"):
        main(p)
