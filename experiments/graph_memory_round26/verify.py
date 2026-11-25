"""Check the preregistered SQuAD replication, sensitivity control and storage receipts."""
import gzip
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent

def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)

def check(path, expected):
    assert path.resolve().is_relative_to(ROOT)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, path

def verify():
    for name in ("directional_replication", "directional_io", "directional_answers"):
        directory = ROOT / name
        manifest = read(next(p for p in (directory / "manifest.json", directory / "MANIFEST_SHA256.json") if p.exists()))
        for relative, digest in manifest.get("files",manifest).items():
            check(directory / relative, digest)
    directory = ROOT / "directional_replication"
    data = read(directory / "results.json")
    check(directory / "per-query.json.gz", data["per_query"])
    rows = read(directory / "per-query.json.gz")
    assert len(rows) == len({r["q"] for r in rows}) == data["n"] == 5304
    assert len({r["t"] for r in rows}) == 442
    assert sum(r["base"] for r in rows) == 4934
    primary = [r["eq"]["both-right"] for r in rows]
    strong = read(directory / "strong-results.json")
    check(directory / "strong-outcomes.json.gz", strong["rows"])
    secondary = [[r["a"], r["b"]] for r in read(directory / "strong-outcomes.json.gz")]
    for pair, expected in ((primary, [5125, 5059, 73, 7]), (secondary, [5125, 5111, 19, 5])):
        assert len(pair) == 5304 and all(a[2] == b[2] <= 256 for a, b in pair)
        assert [sum(a[0] for a,b in pair), sum(b[0] for a,b in pair),
                sum(a[0] > b[0] for a,b in pair), sum(a[0] < b[0] for a,b in pair)] == expected
    directory = ROOT / "directional_io"
    receipt = read(directory / "verification.json")
    for filename, field in (("results.json", "results"), ("online-results.json", "full_service"), ("matched-results.json", "matched")):
        check(directory / filename, receipt[field])
    assert receipt["cases"] == 288
    directory=ROOT/"directional_answers"
    data=read(directory/"results.json")
    check(directory/"per-query.json.gz",data["per_query"])
    rows=read(directory/"per-query.json.gz")
    assert len(rows)==data["n_equal_native"]==data["n_equal_model_compute"]==576
    assert len({r["title"] for r in rows.values()})==48
    for arm, metrics in data["aggregate"].items():
        f1=sum(r["arms"][arm]["f1"] for r in rows.values())/len(rows)
        assert abs(f1*100-metrics["official"]["f1"])<1e-9
    import runpy
    assert runpy.run_path(str(ROOT/"answer_attribution.py"))["compute"]()==read(ROOT/"answer-attribution.json")
    return 3

if __name__ == "__main__":
    print("Verified experiments:", verify())

