"""Check the primary comparisons, disjoint task panels and published artifact receipts."""
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "artifact-digests.json"


def read(name):
    data = (HERE / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def verify_results():
    refs = read("references/results.json")
    assert refs["compared_query_triplets"] == 5880
    groups = refs["groups"]
    original = groups["original/long"]["full"]
    assert [original["demand1024/" + k]["charged"] for k in
            ("copy", "compressed", "eager", "lazy")] == [82907, 82729, 79902, 79893]
    for key, values in (("long", [39868, 37876, 22139, 18005]),
                        ("B", [131923, 129931, 114194, 113179])):
        for mode, expected in zip(("copy", "compressed", "eager", "lazy"), values):
            assert sum(groups[p + "/" + key]["full"]["full/" + mode]["charged"]
                       for p in ("replication", "seed_pair")) == expected
    snapshot_counterexample = read("reference_audit/results.json")["sql"]["counterexample"]["charges"]
    assert (snapshot_counterexample["compressed"], snapshot_counterexample["lazy"]) == (1464, 4484)
    lru = read("lazy/results.json.gz")["external-long"]["all"]["arms"]
    assert (lru["B8-joint-4096"]["charged"], lru["B8"]["queries"]) == (11600, 189)

    streams = read("holdout/events.json.gz")
    assert set(streams) == set(read("holdout/heads.json"))
    assert (len(streams), sum(map(len, streams.values()))) == (6, 4674)
    panel = read("holdout/results.json")["sketch"]
    dense = panel["groups"]["B"]
    for cap, expected in ((1024, [21957, 20055]), (4096, [5911, 7725])):
        assert [dense[f"{cap}/{m}"]["charged"] for m in ("exact", "xor")] == expected
    base, sketch = dense["1024/exact"], dense["1024/xor"]
    assert (sketch["queries"], sketch["recovered0"], sketch["recovered1"],
            sketch["failed"]) == (721, 202, 51, 31)
    assert base["body_bytes"] - sketch["body_bytes"] == 2816
    assert sketch["posting_bytes"] - base["posting_bytes"] == 914
    savings = [row["1024/exact"] - row["1024/xor"] for key, row in
               panel["projects"].items() if key.startswith("B/")]
    assert (sum(savings), sum(x > 0 for x in savings), sum(x == 0 for x in savings)) == (1902, 3, 2)
    sparse = panel["groups"]["long"]
    assert [sparse["1024/" + m]["charged"] for m in ("exact", "xor")] == [3746, 4048]
    admission = read("reconcile/admission-results.json")["groups"]["holdout-B"]
    assert [admission["1024/" + m]["charged"] for m in ("xor", "disabled")] == [20055, 23139]
    opt = read("fast_path/results.json")["measures"]
    assert all(v == 20063 for v in opt["1024/xor_native"]["bytes"])
    assert all(v == 22186 for v in opt["1024/append"]["bytes"])
    assert [round(median(opt["1024/" + m]["combined_ns"]) / 1e6, 2)
            for m in ("append", "xor_native")] == [56.32, 57.87]

    net = read("transport/results.json")
    for cap, expected in ((1024, [(36582, 688), (33180, 670)]),
                          (4096, [(12645, 403), (14721, 423)])):
        for mode, (total, trips) in zip(("exact", "xor"), expected):
            for delay in (0, 2):
                row = net[f"{cap}/{mode}/{delay}"]
                assert row["request_bytes"] + row["reply_bytes"] == row["two_way"] == total
                assert row["round_trips"] == trips and row["queries"] == 721
                assert row["sql_bytes"] == dense[f"{cap}/{mode}"]["charged"]
    audit = read("transport/audit.json")
    assert (audit["runs"], audit["directions"], audit["verified_queries"]) == (144, 288, 17304)

    replays = read("real_sessions/results.json")["all"]["all"]
    cold, selected = (replays["metrics"][m] for m in ("cold", "selective"))
    assert (replays["sessions"], replays["issues"], cold["reads"] - selected["reads"],
            selected["total"] - cold["total"]) == (108, 54, 239, 7919)
    first = read("agent_benchmark/results.json")
    second = read("graph_candidates/results.json")
    assert (first["n"], second["n"], first["distinct_prompts"], second["unique_generations"]) == (57, 33, 167, 68)
    assert read("agent_benchmark/cohort.json.gz")["tasks"].keys().isdisjoint(
        read("graph_candidates/roster.json.gz")["tasks"])
    assert [first["match1"][m] for m in ("true", "flat", "rotation", "qwen27_complete")] == [44, 44, 45, 47]
    assert [(second["matched"][m]["hit5"], second["matched"][m]["match1"])
            for m in ("fusion", "true", "bm25_outcome")] == [(28, 15), (26, 12), (30, 20)]


def verify_release():
    ui = read("demo/ui-check.json")
    assert ui["offline_sha256"] == digest(HERE / "demo/index.html")
    assert (ui["numerical_views_checked"], ui["javascript_errors"], ui["network_requests"]) == (102, 0, 0)
    movie = read("walkthrough/verification.json")
    assert movie["file_sha256"] == digest(HERE / "walkthrough/walkthrough.mp4")
    assert movie["captions_sha256"] == digest(HERE / "walkthrough/captions.srt")
    assert len(movie["verified_scenes"]) == 9
    paper = read("manuscript/verification.json")
    assert paper["pages"] == 4
    assert paper["pdf_sha256"] == digest(HERE / "manuscript/paper.pdf")
    assert read("release/verification.json")["sha256"] == digest(HERE / "release/candidate.zip")


def verify_manifest(seal):
    listing = subprocess.check_output(["git", "ls-files", "-z", "--", "."], cwd=HERE)
    names = sorted(n for n in listing.decode().split("\0") if n and n != MANIFEST.name)
    hashes = {name: digest(HERE / name) for name in names}
    if seal:
        MANIFEST.write_bytes((json.dumps(hashes, indent=2) + "\n").encode())
    else:
        assert hashes == read(MANIFEST.name)
    print(len(hashes), "artifact digests", "written" if seal else "verified")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    options = ap.add_mutually_exclusive_group()
    options.add_argument("--seal", action="store_true")
    options.add_argument("--manifest", action="store_true")
    args = ap.parse_args()
    verify_results()
    verify_release()
    if args.manifest or args.seal:
        verify_manifest(args.seal)
    print("Verified cache measurements, benchmark comparisons and the offline demonstration.")
