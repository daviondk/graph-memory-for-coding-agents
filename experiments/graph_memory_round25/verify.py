"""Recompute released outcomes without external models, documents or benchmarks."""
import gzip
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)

def check(path, expected):
    assert path.resolve().is_relative_to(ROOT), path
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, path

def verify():
    for name in ("directional_open", "release_audit", "external_answers"):
        directory = ROOT / name
        manifest = next(p for p in (directory / "manifest.json", directory / "MANIFEST_SHA256.json") if p.exists())
        metadata = read(manifest)
        for relative, digest in metadata.get("files", metadata).items():
            check(directory / relative, digest)

    directory = ROOT / "sequential_open"
    seal = read(directory / "sequence-lock.json")
    for name, digest in seal["files"].items():
        check(directory / name, digest)
    result = read(directory / "results.json")
    check(directory / "per-query.json.gz", result["outcomes"])
    for corpus, rows in read(directory / "per-query.json.gz")["corpora"].items():
        summary = result["corpora"][corpus]
        assert len(rows) == summary["n"]
        assert sum(r["base"][0] for r in rows.values()) == summary["starting_hits"]
        for method, values in summary["summary"].items():
            assert sum(r["steps"][method][0] for r in rows.values()) == values["hits"]
        for row in rows.values():
            for control in ("any", "first", "frozen", "balanced"):
                assert row["steps"]["tail_eq/" + control][2] == row["steps"]["control_eq/" + control][2]

    directory = ROOT / "query_view"
    seal = read(directory / "query-lock.json")
    check(directory / "decisions.json.gz", seal["decisions"])
    decisions = read(directory / "decisions.json.gz")
    assert len(decisions) == seal["queries"] == 1321
    for row in decisions:
        assert all(value[0] == row["ref"] for name, value in row["arms"].items() if name != "projected")
    data = read(directory / "next-results.json")
    check(directory / "next-outcomes.json.gz", data["outcomes"])
    for corpus, rows in read(directory / "next-outcomes.json.gz").items():
        for name, values in data["summary"][corpus]["metrics"].items():
            assert sum(r["outcomes"][name][0] for r in rows.values()) == values["hits"]
    data = read(directory / "postings-results.json")
    check(directory / "postings-times.json.gz", data["receipt"])
    rows = read(directory / "postings-times.json.gz")
    assert len(rows) == data["logged"]
    for corpus, methods in data["results"].items():
        for method, values in methods.items():
            sample = [v for v in rows if v[0] == corpus and v[3] == method and v[4] == 0]
            assert len(sample) == values["n"]
            assert abs(statistics.fmean(v[6] for v in sample) - values["mean_sql_bytes"]) < 1e-8
            assert abs(statistics.median(v[5] for v in sample) / 1000 - values["p50_us"]) < 1e-8

    directory = ROOT / "external_answers"
    score = read(directory / "results.json")
    rows = read(directory / "per-question.json.gz")
    assert len(rows) == score["n"] == 24
    for method, values in score["aggregate"].items():
        estimates = [r["arms"][method] for r in rows.values()]
        assert abs(statistics.fmean(v["f1"] for v in estimates) - values["official"]["Answer F1"]) < 1e-10
        assert sum(v["em"] for v in estimates) == 4
    return 4

if __name__ == "__main__":
    print("Verified experiments:", verify())

