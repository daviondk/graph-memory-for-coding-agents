"""Lock issue IDs using metadata alone, then fetch their exact source snapshots."""
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CODING = ROOT.parent / "coding"
sys.path.insert(0, str(CODING))
from cache_paths import CACHE
import get_snapshots


def select():
    sys.path.insert(0, str(CACHE / "deps"))
    import pyarrow.parquet as pq
    old = {r["instance_id"] for r in json.loads((CODING / "tasks.json").read_bytes())}
    excluded = old | {"scikit-learn__scikit-learn-10844"}
    cols = ["instance_id", "repo", "base_commit", "problem_statement"]
    verified = {r["instance_id"]: r for r in pq.read_table(CODING / "verified.parquet", columns=cols).to_pylist()}
    repos = defaultdict(list)
    counts = defaultdict(int)
    with (CODING / "bench.final.public.jsonl").open(encoding="utf8") as f:
        for line in f:
            obj = json.loads(line)
            iid = obj["instance_id"]
            if obj["dataset"] == "verified":
                repo = verified[iid]["repo"]
                counts[repo] += 1
                if iid not in excluded:
                    repos[repo].append(iid)
    key = lambda q: hashlib.sha256(("swe-localization-v1|" + q).encode()).hexdigest()
    ids = [q for repo in sorted(repos) for q in sorted(repos[repo], key=key)[:3]]
    assert len(ids) == len(set(ids)) == 30 and not set(ids).intersection(excluded)
    tasks = [verified[q] for q in ids]
    (ROOT / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf8")
    receipt = {"verified_rows": sum(counts.values()), "old_n": len(old), "holdout_n": len(ids),
               "repos": len({row["repo"] for row in tasks}), "excluded_illustration": sorted(excluded-old),
               "tasks_sha256": hashlib.sha256((ROOT / "tasks.json").read_bytes()).hexdigest(),
               "protocol_sha256": hashlib.sha256((ROOT / "protocol.md").read_bytes()).hexdigest()}
    (ROOT / "design_lock.json").write_text(json.dumps(receipt, indent=2), encoding="utf8")
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    select()
    if args.fetch:
        get_snapshots.ROOT = ROOT
        tasks = json.loads((ROOT / "tasks.json").read_bytes())
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(get_snapshots.fetch, tasks))
