"""Validate published timing rows independently without regenerating nondeterministic timings."""
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent

def hashfile(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def csv_rows(name):
    with (BASE/name).open(encoding="utf8",newline="") as f:
        return list(csv.DictReader(f))

def audit():
    d = json.loads((BASE/"results.json").read_text(encoding="utf8"))
    assert hashfile(BASE/"PROTOCOL.md") == d["protocol_sha256"]
    assert hashfile(BASE/"bench.py") == d["benchmark_sha256"]
    assert hashfile(BASE.parent/"predictions.jsonl.gz") == d["lock_sha256"]
    for n,h in d["timing_hashes"].items():
        assert hashfile(BASE/n) == h
    p = csv_rows("physical.csv")
    assert len(p) == len({(r["backend"],r["block"],r["issue"],r["model"],r["group"],r["event"]) for r in p}) == d["verified_physical_outputs"] == 1176
    assert set(Counter((r["backend"],r["block"]) for r in p).values()) == {294}
    m = csv_rows("management.csv")
    prices = {(int(row["block"]),row["policy"]):float(row["ms"]) for row in m}
    assert len(m) == len(prices) == 20
    for contrast,summary in d["management"].items():
        arm,base = contrast.split("-")
        overhead = statistics.median([prices[i,arm]-prices[i,base] for i in range(5)])
        assert math.isclose(overhead, summary["incremental_ms"]["median"])
        assert math.isclose(overhead/summary["hits"],summary["break_even_ms_per_skipped_call"]["median"])
        for backend in ("python","process"):
            for i in range(2):
                use = [r for r in p if r["backend"]==backend and int(r["block"])==i
                       and (arm=="range" or r["also_"+arm]=="1") and (base=="bypass" or r["also_"+base]=="0")]
                full = sum(float(r["ms"]) for r in use)
                assert len(use) == summary["hits"]
                assert math.isclose(full,summary[backend+"_avoided_ms_by_block"][i])
                assert math.isclose(full-overhead,summary[backend+"_net_ms_vs_median_management"][i])
    for backend,x in d["physical_ms_per_call"].items():
        a = sorted(float(r["ms"]) for r in p if r["backend"]==backend)
        assert math.isclose(statistics.median(a),x["median"])
        assert math.isclose(statistics.mean(a),x["mean"])
        assert math.isclose(a[math.ceil(.95*len(a))-1],x["p95"])
    print("PASS: 1,176 physical rows, 20 management runs, four contrasts, hashes and all reported signs verified.")

if __name__=="__main__":
    audit()

