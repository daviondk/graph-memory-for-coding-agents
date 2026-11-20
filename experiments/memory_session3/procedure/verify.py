"""Audit sealed prospective predictions by streaming each original projected tool outcome."""
import csv
import gzip
import hashlib
import itertools
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "verification"))
from run import selector
from replay import parse_read


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parsed_lines(stream):
    return (json.loads(line) for line in stream)


def audit():
    direct = read("prediction_lock.json")
    for name, hashed in direct["files"].items():
        assert digest(ROOT / name) == hashed, name
    tests = read("verification/lock.json")
    for key, name in {"protocol": "verification/PROTOCOL.md", "code": "verification/run.py",
                      "predictions": "verification/predictions.jsonl.gz", "source_hash": "sources.json"}.items():
        assert digest(ROOT / name) == tests[key], name
    original = read("sources.json")
    verified = {}
    test_stats = Counter()
    read_stats = defaultdict(Counter)
    groups = defaultdict(Counter)
    counts = Counter()
    with gzip.open(ROOT / "predictions.jsonl.gz", "rt", encoding="utf8") as hints, \
            gzip.open(ROOT / "verification/predictions.jsonl.gz", "rt", encoding="utf8") as choices, \
            gzip.open(ROOT / "verification/reference.jsonl.gz", "rt", encoding="utf8") as truths:
        reads, proposals, references = map(parsed_lines, [hints, choices, truths])
        for source in original:
            model, issue = source["model"], source["id"]
            path = ROOT / "events" / model / (issue + ".json.gz")
            verified[path.relative_to(ROOT).as_posix()] = digest(path)
            with gzip.open(path, "rt", encoding="utf8") as f:
                doc = json.load(f)
            assert doc["source"] == source and doc["verified_cwd"] == "/testbed"
            for i, batch in enumerate(doc["groups"]):
                tests_in_batch = []
                last_correct = {}
                for j, e in enumerate(batch):
                    counts["calls"] += 1
                    r = e["result"]
                    if r is not None and "text" in r:
                        payload = r["text"].encode("utf8")
                        assert r["visible"] and hashlib.sha256(payload).hexdigest() == r["sha"]
                        assert len(payload) == r["bytes"]
                    target = selector(e["command"])
                    if target:
                        tests_in_batch.append((j,target[0]))
                    if not parse_read(e["command"]):
                        continue
                    hint = next(reads)
                    assert (hint["id"],hint["model"],hint["batch"],hint["j"]) == (issue,model,i,j)
                    assert r is not None
                    counts["supported"] += 1
                    groups[issue]["supported"] += 1
                    for m in ["literal","exact","contained","range","optimistic","coarse"]:
                        h = hint["pred"].get("main/"+m)
                        correct = bool(h and h == r["sha"] and r["rc"] == 0)
                        sums = read_stats[m]
                        sums["n"] += 1
                        sums["attempted"] += int(bool(h))
                        sums["correct"] += int(correct)
                        sums["stale"] += int(bool(h) and not correct)
                        sums["correct_bytes"] += r["bytes"] if correct else 0
                        groups[issue][m] += int(correct)
                if len(tests_in_batch) != 1:
                    continue
                j,t = tests_in_batch[0]
                row, ref = next(proposals), next(references)
                for entry in (row,ref):
                    assert (entry["id"],entry["model"],entry["i"],entry["j"]) == (issue,model,i,j)
                assert t == ref["truth"] and len(row["bank"]) <= 8
                test_stats["n"] += 1
                for m, pred in row["choices"].items():
                    assert pred is None or pred in row["bank"]
                    test_stats[m] += int(pred == t)
        assert all(next(it,None) is None for it in (reads,proposals,references))
    assert len(verified) == len(original) == 1441
    assert len({x["id"] for x in original}) == 500
    existing = read("results.json")["metrics"]["pooled"]
    assert all(dict(s) == existing["main/"+m] for m,s in read_stats.items())
    actual_tests = read("verification/results.json")["pooled"]
    assert all(actual_tests[k] == n for k,n in test_stats.items())
    # Post hoc descriptive contrast with the stronger one-record containment control.
    pairs = [(v["range"]-v["contained"], v["supported"]) for v in groups.values()]
    assert all(n >= 0 for n,d in pairs)
    rng = random.Random(17112026)
    runs = []
    for _ in range(4000):
        samples = rng.choices(pairs,k=len(pairs))
        runs.append(100*sum(v for v,_ in samples)/sum(d for _,d in samples))
    runs.sort()
    manifest = ROOT / "projected_manifest.json"
    if manifest.exists():
        assert verified == read(manifest)
    else:
        manifest.write_text(json.dumps(verified,indent=1)+"\n",encoding="utf8")
    return {
        "status": "pass", "source_sessions": len(verified),
        "total_source_bytes": sum(s["bytes"] for s in original),
        "total_projected_gzip_bytes": sum((ROOT / item).stat().st_size for item in verified),
        "unique_repo_names": len({x["id"].rsplit("-",1)[0] for x in original}),
        "total_calls": counts["calls"], "eligible_reads": counts["supported"],
        "verification": dict(test_stats),
        "paired_range_minus_single_record_posthoc": {
            "issues_with_any_eligible_read":len(pairs), "improved":sum(v>0 for v,_ in pairs),
            "worse":sum(v<0 for v,_ in pairs), "difference":sum(v for v,_ in pairs),
            "ci95_pp": [runs[100],runs[3899]], "bootstrap_replicates":4000},
        "projected_manifest_sha256":digest(manifest)
    }


if __name__ == "__main__":
    print(json.dumps(audit(),indent=2))

