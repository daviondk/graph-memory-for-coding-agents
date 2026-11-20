"""Build the small audit tables from an unpacked round-6 work directory."""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        yield from map(json.loads, stream)


def save(path, values):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), file=stream)


def main(source, target):
    archive = source / "published"
    sys.path.insert(0, str(archive))
    from hybrid_score import decode, wire
    target.mkdir(exist_ok=True, parents=True)
    rendered = dict(rows(archive / "external/symmetric/rendered.jsonl.gz"))
    metrics = {r["key"]: r for r in rows(archive / "symmetric_paired.jsonl.gz")}
    times = {r["key"]: r["us"] for r in
             map(json.loads, (source / "latency/times_native.jsonl").read_text().splitlines())}
    records = []
    for q in rows(archive / "external/queries.jsonl.gz"):
        if q["kind"] != "edit":
            continue
        key = q["key"]
        answer = rendered[key]
        cold = wire(q, decode(q, answer["multiple"]))
        route = answer["hybrid"]
        if route["route"] == "hot":
            hybrid = wire(q, json.loads(route["response"])["lines"])
        else:
            hybrid = wire(q, decode(q, route["response"]))
        assert cold == hybrid
        measures = metrics[key]
        records.append({
            "query": key, "task": q["id"], "project": q["repo"], "route": route["route"],
            "historical_full": measures["m"]["multiple"]["full"],
            "updated_full": measures["m"]["sym_archive"]["full"],
            "historical_wrong_lines": measures["m"]["multiple"]["wrong"],
            "updated_wrong_lines": measures["m"]["sym_archive"]["wrong"],
            "archive_pages": measures["cost"]["sym_archive"]["pages"],
            "hybrid_pages": measures["cost"]["sym_hybrid"]["pages"],
            "archive_sha256": hashlib.sha256(cold).hexdigest(),
            "hybrid_sha256": hashlib.sha256(hybrid).hexdigest(),
            "wire_bytes": len(cold), "us": times[key]})
    save(target / "memtrace.jsonl", records)
    repair = source / "repair"
    equal = {r["id"]: r["equal_pass"] for r in json.loads((repair / "equal_paths.json").read_bytes())["rows"]}
    primary = [{"task": r["id"], "control_valid": r["valid"],
                "text": r["arms"]["flat"]["passed"], "graph": r["arms"]["graph"]["passed"],
                "shuffled": r["arms"]["shuffled"]["passed"], "oracle_same_paths": equal[r["id"]]}
               for r in json.loads((repair / "per_task.json").read_bytes())]
    save(target / "sympy.jsonl", primary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    main(args.source.resolve(), args.target.resolve())

