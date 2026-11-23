"""Compute the published file-level confusion counts without interpreting a dependency as a failure."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean
import subprocess

ROOT = Path(__file__).resolve().parent
REV = "f1acdae0f2b2d1ed6e3e2956d510db49bb7c276f"
CODES = dict(dask="DAS", loguru="LOG", matplotlib="MA", pvlib="PVL", pylint="PYL",
             seaborn="SE", sklearn="SC", sphinx="SPH", sympy="SY", xarray="XA")
METHODS = ["NameRTS", "EkstaP", "BabelRTS"]


def encode(obj):
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def files_of(row):
    names = row["tests_to_run"]
    assert all(name and "\\" not in name and not name.startswith(("/", "./")) for name in names), row["current"]
    return set(names)


def summarize(rows):
    raw = Counter()
    for r in rows:
        for key in ("n", "gold", "selected", "hit", "extra", "missed", "full", "safe", "exact"):
            raw[key] += r[key]
    extra_full = sum(r["extra"] for r in rows if r["full"])
    raw.update(rows=len(rows), extra_on_full=extra_full,
               true_parents=len({(r["project"], r["true_parent"]) for r in rows}))
    return dict(raw, mean_reduction=mean(1-r["selected"]/r["n"] for r in rows),
                mean_extra_fraction=mean(r["extra"]/r["n"] for r in rows),
                share_extra_on_full=extra_full/raw["extra"] if raw["extra"] else None)


def run(repo):
    assert subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip() == REV
    sources = {}
    anomalies = []
    rows = []
    for project, code in CODES.items():
        babel = "scikit-learn" if project == "sklearn" else project
        files = {"gold": f"ground truth/gt_{project}.json",
                 "NameRTS": f"results/rq1/namerts/NameBDP_RTSTest_{code}.json",
                 "EkstaP": f"results/rq1/ekstap/EkstaP_RTSTest_{code}.json",
                 "BabelRTS": f"results/rq1/babelrts/BabelRTS_{babel}_clearn.json"}
        tables = {}
        for method, path in files.items():
            data = subprocess.check_output(["git", "-C", repo, "show", f"{REV}:{path}"])
            raw = json.loads(data)
            sources[path] = {"sha256": digest(data), "rows": len(raw)}
            keep = [r for r in raw if method != "gold" or r["target"]]
            tables[method] = {r["current"]: r for r in keep}
            assert len(keep) == len(tables[method]), (project, method, "duplicate revisions")
        for method in METHODS:
            assert set(tables[method]) == set(tables["gold"]), (project, method, "different revisions")
        for sha, gold in sorted(tables["gold"].items()):
            g = files_of(gold)
            n = gold["total_tests"]
            assert 0 <= len(g) <= n and n > 0
            for method in METHODS:
                pred = tables[method][sha]
                assert all(pred[k] == gold[k] for k in ("true_parent", "direct_parent")), (project, method, sha)
                selected = files_of(pred)
                if len(selected) > n or len(pred["tests_to_run"]) != len(selected) or len(gold["tests_to_run"]) != len(g):
                    anomalies.append([project, sha, method, n, len(selected), len(pred["tests_to_run"]), len(g), len(gold["tests_to_run"])])
                rows.append(dict(project=project, sha=sha, true_parent=gold["true_parent"], direct_parent=gold["direct_parent"],
                                 method=method, n=n, gold=len(g), selected=len(selected), hit=len(g & selected),
                                 extra=len(selected-g), missed=len(g-selected), full=len(selected)==n,
                                 safe=g <= selected, exact=g==selected))
    by_project = {p: {m: summarize([r for r in rows if r["method"]==m and r["project"]==p])
                      for m in METHODS} for p in CODES}
    overall = {m: summarize([r for r in rows if r["method"]==m]) for m in METHODS}
    (ROOT/"sources.json").write_bytes(encode({"revision": REV, "files": sources}) + b"\n")
    (ROOT/"counts.json.gz").write_bytes(gzip.compress(encode(rows), mtime=0))
    (ROOT/"results.json").write_bytes(encode(dict(by_project=by_project, overall=overall, anomalies=anomalies)) + b"\n")
    print("Totals", json.dumps(overall))
    print("Anomalies", len(anomalies), anomalies[:2])
    print("NameRTS per project")
    for p,v in by_project.items():
        s=v["NameRTS"]
        print(p, s["rows"], s["gold"], s["selected"], s["extra"], s["missed"], s["full"], s["extra_on_full"], s["exact"], s["true_parents"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    run(parser.parse_args().repo)

