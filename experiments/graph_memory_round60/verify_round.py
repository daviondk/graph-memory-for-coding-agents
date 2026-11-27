"""Cross-check round-level claims against component measurements and the shipped release."""
import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path
from statistics import median
import subprocess
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
MANIFEST = "artifact-digests.json"


def read(name):
    data = (HERE / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def digest(name):
    return sha256((HERE / name).read_bytes()).hexdigest()


def results():
    panel = read("panel/panel.json")
    assert digest("panel/events.json.gz") == panel["archive_sha256"]
    assert [panel["totals"][k] for k in ("transitions", "eligible", "post_dense", "post_sparse")] == [3566, 966, 485, 45]
    coverage = read("coverage/results.json")
    for key, expected in [("old12/B", [123019,115945,109005]), ("r59/B", [21957,20055,17177]),
                          ("new/B", [11531,10465,9213])]:
        assert [coverage[key]["arms"]["1024/" + m]["charged"] for m in ("exact","xor","notify")] == expected
    proof = read("coverage/audit.json")
    assert proof["state_and_faults"]["resident_postings_checked"] == 5778
    assert [s["sql_postings"] for s in proof["drop_five"]] == [1,0]
    fmt = read("succinct/results.json")["new/B"]
    assert [fmt["1024/" + m]["charged"] for m in ("exact/basic", "exact/best", "notify/basic", "notify/best")] == [11531,11372,9213,9201]
    for m in ("exact/best", "notify/best"):
        assert fmt["4096/" + m]["charged"] == 4322
    queue = read("eviction/results.json")["new/B"]
    assert [queue["1024/sieve/" + m]["charged"] for m in ("exact","xor","notify")] == [11561,12699,9174]
    adapt = read("adaptive/results.json")["groups"]["new/B"]
    assert sum(adapt[k]["charged"] for k in ("1024/adaptive", "4096/adaptive")) == 15467
    assert sum(adapt[k]["charged"] for k in ("1024/xor", "4096/exact")) == 14787
    measured = read("hot_delta/results.json")["new/B"]
    assert [measured["1024/" + m]["charged"][0] for m in ("append", "notify", "hot_trusted")] == [11646,9213,10863]
    opt = read("fast_coverage/hit-results.json")["both"]["methods"]
    for mode, counted, ms in [("resident_hit",26122,91.43), ("full_reuse",33837,94.60), ("hot_only",38402,84.77)]:
        x = opt["1024/" + mode]
        assert x["traffic"] == [counted] * 5 and round(median(x["total_ns"]) / 1e6,2) == ms
    wire = read("wire/results.json")["arms"]
    for cap, records in [(1024,[(20115,412),(17919,386),(16533,374)]), (4096,[(9146,281),(10677,294),(9146,281)])]:
        for mode, (amount, trips) in zip(("exact","xor","notify"), records):
            for delay in (0,2):
                q = wire[f"{cap}/{mode}/{delay}"]["counters"]
                assert q["wire"] == amount == q["request"] + q["reply"] and q["trips"] == trips
                assert q["posting_bytes"] + q["body_bytes"] == coverage["new/B"]["arms"][f"{cap}/{mode}"]["charged"]
    assert read("wire/audit.json")["checked"]["per_query_transcripts"] == 20370
    observed = read("observed_coverage/results.json")
    assert all(x["charged"] == 1668 and x["query"] == 436 for x in observed["16/1024"]["methods"].values())
    assert [observed["4/256"]["methods"][m]["charged"] for m in ("exact","xor","notify")] == [7798,7650,7636]
    lite = read("benchmark/results.json")["lite"]["results"]
    assert [(lite[m]["any"], lite[m]["calls"], lite[m]["input"]) for m in ("full_three", "full")] == [(73,31,104401),(75,99,336189)]
    assert lite["fusion"]["any"] == 65


def release():
    ui = read("demo/ui-check.json")
    assert ui["html_sha256"] == digest("demo/index.html") and ui["external_requests"] == ui["javascript_errors"] == 0
    video = read("walkthrough/verification.json")
    assert video["file_sha256"] == digest("walkthrough/walkthrough.mp4")
    assert video["captions_sha256"] == digest("walkthrough/captions.srt") and len(video["verified_scenes"]) == 9
    doc = read("manuscript/verification.json")
    assert doc["page_count"] == 4 and doc["sha256"]["paper.pdf"] == digest("manuscript/paper.pdf")
    assert read("release/verification.json")["sha256"] == digest("release/candidate.zip")
    with ZipFile(HERE / "release/candidate.zip") as z:
        assert z.testzip() is None and z.read("paper.pdf") == (HERE / "manuscript/paper.pdf").read_bytes()
        assert z.read("source.sqlite") == (HERE / "release/source.sqlite").read_bytes()


def manifest(seal):
    files = subprocess.check_output(["git","ls-files","-z","--","."],cwd=HERE).decode().split("\0")
    values = {name:digest(name) for name in sorted(files) if name and name != MANIFEST}
    if seal:
        (HERE / MANIFEST).write_bytes((json.dumps(values,indent=2) + "\n").encode())
    else:
        assert values == read(MANIFEST)
    print(len(values), "versioned artifacts", "sealed" if seal else "verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--seal", action="store_true")
    options.add_argument("--manifest", action="store_true")
    args = parser.parse_args()
    results()
    release()
    if args.seal or args.manifest:
        manifest(args.seal)
    print("Verified the main comparisons, official Lite retrieval counts, manuscript, video and SQLite release.")
