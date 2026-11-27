"""Cross-check the R56 paper numbers; optionally verify the Git artifact manifest."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "artifact-digests.json"


def read(name):
    payload = (HERE / name).read_bytes()
    if name.endswith(".gz"):
        payload = gzip.decompress(payload)
    return json.loads(payload)


def metrics():
    shared = read("shared_evidence/results.json")
    paired = read("shared_evidence/paired.json")
    intersections = read("event_intersection/results.json")
    sketches = read("pair_bounds/results.json")
    durable = read("durable/results.json")
    panels = {"A": 1075, "B": 880, "C": 1216, "long": 196}
    for panel, n in panels.items():
        own = shared[panel + "8"]["pooled"]
        assert own["n"] == n
        assert own["methods"]["full"]["exact_ids_scores"] == n
        for budget in (8, 25):
            ref = intersections[panel + str(budget)]["pooled"]
            assert ref["n"] == n
            assert abs(ref["recall"] - own["methods"]["full"]["recall"]) < 1e-12
        if panel != "long":
            assert abs(sketches[panel + "8"]["pooled"]["recall"] - ref["recall"]) < 1e-12
        pair = paired[panel]["last_shared-last_own"]["pooled"]
        assert pair["wins"] + pair["ties"] + pair["losses"] == n
        assert abs(pair["delta_pp"] - 100 * (own["methods"]["last_shared"]["recall"]
                                            - own["methods"]["last_own"]["recall"])) < 1e-10
    for panel in ("B", "long"):
        for medium in ("ram", "wal"):
            reads = read(f"shared_evidence/physical-{medium}-summary.json")[panel]
            for physical, mode in (("packed", "full"), ("own_archive", "own"), ("shared_archive", "split")):
                recorded = durable[f"{panel}-1-{mode}"]["counts"]
                for key in ("sql", "rows", "payload"):
                    assert reads[physical][key] == recorded[key]
                    assert durable[f"{panel}-8-{mode}"]["counts"][key] == 8 * recorded[key]
    assert [durable[k]["bytes"] // 1024 for k in ("B-1-full","B-1-split",
                                                   "long-1-full","long-1-split")] == [196,200,664,500]
    assert read("event_intersection/long-git-audit.json")["total_transitions"] == 12288
    assert read("event_intersection/sharpness.json")["pairs"] == 262143
    passes = read("solver/results.json")["summaries"]
    assert [passes[mode]["pass1"] for mode in ("contract", "file8", "full_bm25")] == [13, 15, 15]
    assert passes["file8"]["examples"] == 178
    size = read("size_control/results.json")
    for panel, n in panels.items():
        stats = size[panel]["all"]
        assert len(stats) == 12 and all(v["n"] == n for v in stats.values())
        reference = shared[panel + "8"]["pooled"]["methods"]
        for mode, ref in (("own", "last_own"), ("small", "last_small")):
            assert abs(stats[mode]["recall"] - reference[ref]["recall"]) < 1e-12
            assert stats[mode]["events"] == reference[ref]["decoded_events"]
    long_results = size["long"]["all"]
    assert [round(100 * long_results[key]["recall"], 2)
            for key in ("small", "cap8", "small_norm", "fill6_norm")] == [45.88, 47.32, 47.61, 48.90]
    assert read("code2test/results.json")["scope"]["eligible_n"] == 105
    print("Four panels agree on full-history retrieval. Exact read counters, bytes, task counts and published endpoint scores agree across artifacts.")


def tracked_paths():
    # Use the Git index to exclude caches, timing databases and compiler intermediates.
    raw = subprocess.check_output(["git", "ls-files", "-z", "--", "."], cwd=HERE)
    return [part.decode("utf-8") for part in raw.split(b"\0") if part]


def manifest(seal):
    if seal:
        names = [name for name in tracked_paths() if name != MANIFEST.name]
    else:
        known = read(MANIFEST.name)
        names = list(known)
    hashes = {key: hashlib.sha256((HERE / key).read_bytes()).hexdigest() for key in sorted(names)}
    if seal:
        MANIFEST.write_text(json.dumps(hashes, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    elif hashes != known:
        raise ValueError("The artifact manifest does not match this checkout.")
    print(f"{len(hashes)} file digests {'written' if seal else 'verified'}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    option = parser.add_mutually_exclusive_group()
    option.add_argument("--seal", action="store_true")
    option.add_argument("--manifest", action="store_true")
    flags = parser.parse_args()
    metrics()
    if flags.seal or flags.manifest:
        manifest(flags.seal)
