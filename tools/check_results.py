"""Recompute headline comparisons from paired observations using only the standard library."""
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return [json.loads(line) for line in (ROOT / "results" / name).read_text(encoding="utf-8").splitlines()]


def main():
    reads = read("memtrace.jsonl")
    repairs = read("sympy.jsonl")
    assert len({r["query"] for r in reads}) == len(reads) == 186
    assert len({r["task"] for r in reads}) == 48 and len({r["project"] for r in reads}) == 12
    assert all(r["archive_sha256"] == r["hybrid_sha256"] for r in reads)
    counts = {k: sum(r[k] for r in reads) for k in
              ("historical_full", "updated_full", "historical_wrong_lines", "updated_wrong_lines",
               "archive_pages", "hybrid_pages", "wire_bytes")}
    assert list(counts.values()) == [121, 129, 113, 2, 141, 11, 94629]
    milliseconds = {a: mean(median(r["us"][a]) / 1000 for r in reads)
                    for a in ("archive", "routed", "lru")}
    assert len({r["task"] for r in repairs}) == len(repairs) == 16 and all(r["control_valid"] for r in repairs)
    passes = {k: sum(r[k] for r in repairs) for k in ("text", "graph", "shuffled", "oracle_same_paths")}
    assert list(passes.values()) == [4, 3, 3, 10]
    print(json.dumps({"known_address": counts, "linux_mean_ms": milliseconds, "sympy_16": passes},
                     indent=2))


if __name__ == "__main__":
    main()

