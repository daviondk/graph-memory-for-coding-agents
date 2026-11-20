"""Diagnostic only. This program opens input-only snapshots, before disjoint-panel scoring."""
import hashlib
import sys
from pathlib import Path
import rank

ROOT = Path(__file__).resolve().parent

def main():
    original = rank.adjacency
    def uniform(evidence, seeds):
        return original(evidence, {p: 1 / len(evidence) for p in evidence})
    rank.adjacency = uniform
    for panel in (ROOT, ROOT / "replication"):
        rank.D = panel
        inputs = rank.load("inputs.json.gz")
        rows = {r["id"]: rank.calculate(r)[0]["graph"] for r in inputs}
        rank.dump("uniform_rankings.json.gz", rows)
        names = ("uniform_rankings.json.gz", "inputs.json.gz")
        sig = {n: rank.h((panel / n).read_bytes()) for n in names}
        sig["centrality.py"] = rank.h(Path(__file__).read_bytes())
        sig["MECHANISM_RU.md"] = rank.h((ROOT / "MECHANISM_RU.md").read_bytes())
        rank.dump("uniform.lock.json", sig)
    rank.adjacency = original

if __name__ == "__main__":
    main()
