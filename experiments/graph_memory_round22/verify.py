"""Recompute the public report's headline counts from the compact archived outputs."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def read(path):
    raw = (ROOT / path).read_bytes()
    return json.loads(gzip.decompress(raw) if path.endswith(".gz") else raw)

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

def verify():
    for study in ("observed_flow", "threshold_read", "conditional_lookup/adaptive"):
        for name, digest in read(f"{study}/MANIFEST_SHA256.json").items():
            assert sha(f"{study}/{name}") == digest, (study, name)

    lock = read("prefix_read/forecast-lock.json")
    assert lock["native_history_checks"] == 191
    for name, digest in lock["files"].items():
        assert sha(f"prefix_read/{name}") == digest
    prefixes = read("prefix_read/outcomes.json.gz")
    assert sha("prefix_read/outcomes.json.gz") == read("prefix_read/results.json")["outcomes"]
    assert Counter(r["cut"] for r in prefixes) == {pct: 2000 for pct in (25, 50, 75, 100)}
    panel = [r for r in prefixes if r["cut"] == 50 and r["eligible"] and not r["pilot"]]
    assert (len(panel), len({r["t"] for r in panel})) == (901, 657)
    assert all(arm["tokens"] <= 2048 for r in prefixes for arm in r["arms"].values())
    assert [sum(r["arms"][method]["fs"] for r in panel)
            for method in ("exact", "final", "append", "dense")] == [732, 737, 719, 682]

    choices = read("action_reader/reader-lock.json")
    assert choices["responses"] == sha("action_reader/choices.json.gz")
    assert len(read("action_reader/choices.json.gz")) == choices["n"] == 238
    stats = read("action_reader/results.json")
    assert sha("action_reader/outcomes.json.gz") == stats["per_query"]
    assert sha("action_reader/reader-lock.json") == stats["source"]
    actions = read("action_reader/outcomes.json.gz")
    labelled = [r for r in actions if r["n_targets"]]
    assert (len(actions), len(labelled), len({r["family"] for r in labelled})) == (77, 45, 18)
    assert sum(len(r["returned_write_hashes"]) for r in actions) == 308
    assert [sum(r["arms"][a] for r in labelled) for a in
            ("name_index/normal", "fifo/normal", "name_index/rule", "name_index/reverse")] == [41, 36, 40, 39]

    audit = read("audit-readers.json")
    assert audit["dp_exhaustive_checks"] == 189
    assert audit["sql"]["verified_lookups"] == 308
    assert audit["sql"]["paired_family_flip_p_two_sided"] == 0.125
    native = read("threshold_read/native-results.json")
    assert native["real_comparisons"] == 20000 and native["synthetic_comparisons"] == 1280
    assert native["totals"]["prefix/stream"]["rows"] == 67091
    assert native["totals"]["prefix/vector"]["rows"] == 249089
    source = "conditional_lookup/"
    lookup = read(source + "results.json")
    assert lookup["outcomes"] == sha(source + "outcomes.json.gz")
    assert read(source + "forecast-lock.json")["forecast"] == sha(source + "forecasts.json.gz")
    assert lookup["forecast_lock"] == sha(source + "forecast-lock.json")
    pairs = read(source + "outcomes.json.gz")
    active = [p for p in pairs if p["reachable"]]
    assert (len(pairs), sum(p["labelled"] for p in pairs), len(active)) == (449, 377, 271)
    assert len({p["family"] for p in active}) == 164
    assert [sum(p["methods"][m]["hit2"] for p in active)
            for m in ("bm25", "e5", "hybrid", "signature", "neighbor")] == [177, 169, 180, 178, 185]
    assert read(source + "family-sensitivity.json")["components"] == 155
    wire = read(source + "budget-outcomes.json.gz")
    assert len(wire) == 3 * 7 * len(active) and all(0 <= v["bytes"] <= v["budget"] for v in wire)
    assert read(source + "budget-results.json")["per_query_sha"] == sha(source + "budget-outcomes.json.gz")
    adaptive = read(source + "adaptive/results.json")["primary"]
    assert (adaptive["components"], adaptive["arms"]["adaptive"]["hit2"], adaptive["arms"]["neighbor"]["hit2"]) == (155,185,185)
    split = read("native_multiseed/official580/split-audit.json")
    assert split["split"] == sha("native_multiseed/official580/split.json.gz")
    for name, expected in (("train", 3894),("test", 2000)):
        both = split["splits"][name]
        assert both["local"] == both["official"] and both["local"]["n"] == expected
    dev = split["splits"]["dev"]
    assert (dev["local"]["n"],dev["official"]["n"]) == (500,580)
    return {"prefix_forecasts": len(prefixes), "main_prefix_panel": len(panel),
            "conditional_lookup_panel": len(active), "source_lookups": stats["executed_indexed_lookups"], "physical_comparisons": native["real_comparisons"]}

if __name__ == "__main__":
    print(json.dumps(verify()))

