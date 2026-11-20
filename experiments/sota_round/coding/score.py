"""Score already frozen prediction files using the pinned SWE-Explore evaluator."""
import csv
import hashlib
import json
import random
import statistics as st
import sys
import tarfile
from collections import defaultdict
from pathlib import Path
from cache_paths import CACHE

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "upstream"))
from eval import ExploreEvaluator

METRICS = ["f1_score", "precision", "recall", "hit_file_rate", "hit_region_rate", "noise_file_rate", "recall_at_300"]


def line_counts(iid, gt):
    core = gt.get("read_core_regions") or []
    optional = gt.get("read_optional_regions_map") or {}
    regions = list(core) + [r for v in optional.values() for r in v]
    needed = {r["path"] for r in regions if r["start"] < 0 or r["end"] == -1}
    counts = {}
    for name in list(needed):
        path = CACHE / "snapshots" / iid / name
        if path.is_file():
            counts[name] = len(path.read_text(encoding="utf8", errors="ignore").splitlines())
    missing = needed - counts.keys()
    if missing:
        with tarfile.open(CACHE / "archives" / (iid + ".tar.gz")) as archive:
            for member in archive:
                name = member.name.partition("/")[2]
                if name in missing and member.isfile():
                    counts[name] = len(archive.extractfile(member).read().decode("utf8", errors="ignore").splitlines())
    return counts


def main():
    tasks = json.loads((ROOT / "tasks.json").read_text(encoding="utf8"))
    ids = [t["instance_id"] for t in tasks]
    predictions = {q: json.loads((ROOT / "predictions" / (q + ".json")).read_bytes()) for q in ids}
    pred_sha = hashlib.sha256(json.dumps({q:[v["bm25"],v["fusion"]] for q,v in predictions.items()}, sort_keys=True).encode()).hexdigest()
    for arm in ["bm25", "fusion"]:
        assert all(len(value[arm]) == 5 and all(1 <= b-a+1 <= 80 for _,a,b in value[arm]) for value in predictions.values())
    benchfile = ROOT / "bench.final.public.jsonl"
    assert hashlib.sha256(benchfile.read_bytes()).hexdigest() == "dc4f114ececd0bfb987361c26ae5e2440456e2cccb36adfccb09ea5385aec202"
    ev = ExploreEvaluator(benchfile)
    ev.file_line_counts = {q:line_counts(q, ev.bench_data_dict[q]["ground_truth"]) for q in ids}
    scores = {arm:ev.evaluate(lambda _issue, q:predictions[q][arm], ids, METRICS) for arm in ["bm25", "fusion"]}
    report = {"n": len(ids), "n_repos": len({t["repo"] for t in tasks}), "prediction_sha256": pred_sha,
              "protocol_sha256": hashlib.sha256((ROOT / "protocol.md").read_bytes()).hexdigest()}
    report["means"] = {arm:{metric:st.mean(result[q][metric] for q in ids) for metric in METRICS} for arm,result in scores.items()}
    diffs = {q:scores["fusion"][q]["f1_score"] - scores["bm25"][q]["f1_score"] for q in ids}
    groups = defaultdict(list)
    for task in tasks:
        groups[task["repo"]].append(diffs[task["instance_id"]])
    repos = sorted(groups)
    rng = random.Random(20261116)
    boot = []
    for _ in range(10000):
        sampled = rng.choices(repos, k=len(repos))
        boot.append(st.mean(v for repo in sampled for v in groups[repo]))
    bounds = st.quantiles(boot, n=40, method="inclusive")
    report["paired_primary"] = {"difference": st.mean(diffs.values()), "repo_bootstrap_95": [bounds[0],bounds[-1]],
                                "wins": sum(v > 0 for v in diffs.values()), "ties": sum(v == 0 for v in diffs.values()),
                                "losses": sum(v < 0 for v in diffs.values())}
    report["secondary_excluding_memdev_illustrated_issue"] = st.mean(v for k,v in diffs.items() if k != "pydata__xarray-4687")
    report["budget"] = {arm:{"mean_emitted_regions":st.mean(len(p[arm]) for p in predictions.values()),
                             "mean_raw_lines_counting_overlap":st.mean(sum(b-a+1 for _,a,b in p[arm]) for p in predictions.values())}
                        for arm in scores}
    with (ROOT / "score_rows.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=["instance_id","repo","method",*METRICS])
        w.writeheader()
        for task in tasks:
            for arm,result in scores.items():
                q=task["instance_id"]
                w.writerow({"instance_id":q,"repo":task["repo"],"method":arm,**result[q]})
    (ROOT / "results.json").write_text(json.dumps(report,indent=2),encoding="utf8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
