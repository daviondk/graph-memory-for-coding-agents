"""Freeze an input-only sample from the preceding fully materialized graph oracle, then validate."""
import collections
from concurrent.futures import ProcessPoolExecutor, as_completed
import gzip
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

from lazy_git import evaluate, METHODS

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def read_reference(repo):
    path = SOURCE / "shards" / (repo + ".jsonl.gz")
    return [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines() if line]


def key(row):
    return tuple(row[k] for k in ("repo", "before", "after", "s", "t"))


def freeze():
    lock = json.loads((SOURCE / "input_lock.json").read_text(encoding="utf-8-sig"))
    receipt = json.loads((SOURCE / "receipt.json").read_text(encoding="utf-8-sig"))
    shard_digests = {r["repo"]: r["sha256"] for r in receipt["repositories"]}
    groups = []
    for repo, group, path, head, _ in lock:
        refs = read_reference(repo)
        assert digest((SOURCE / "shards" / (repo + ".jsonl.gz")).read_bytes()) == shard_digests[repo]
        keys = sorted((key(r) for r in refs), key=lambda k:digest("|".join(("G3-L-20261118", *k)).encode()))[:10]
        groups.append(dict(repo=repo, group=group, path=path, head=head, keys=keys, source_sha=shard_digests[repo]))
    payload = {"input": groups, "protocol_sha": digest((ROOT/"PROTOCOL.md").read_bytes())}
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf8")
    file = ROOT / "sample.lock.json"
    if file.exists():
        assert file.read_bytes() == encoded
    else:
        file.write_bytes(encoded)
    return groups


def work(group):
    repo = group["repo"]
    ref = {key(r): r for r in read_reference(repo)}
    out_rows = []
    for k in group["keys"]:
        (_, old, new, s, t) = k
        val = evaluate(group["path"], old, new, s, t)
        row = ref[tuple(k)]
        checks = {"old_truth": val["direct_old"]["outcome"] is True,
                  "new_truth": val["direct_new"]["outcome"] == bool(row["truth"])}
        for method in METHODS:
            arm = val[method]
            checks[method] = {
                "truth": arm["read"]["outcome"] == bool(row["truth"]),
                "fast": arm["read"]["fast"] == bool(row[method]["fast"]),
                "verified": arm["read"]["validated"] == bool(row[method]["validated"]),
                "paths": [list(p) for p in arm["certificate"]["proofs"]] == row[method]["proofs"],
                "zero_fast": not arm["read"]["fast"] or arm["read"]["counts"].get("blob_objects", 0) == 0}
        wrong = [name for name, v in checks.items() if (not all(v.values()) if isinstance(v,dict) else not v)]
        out_rows.append(dict(key=k,group=group["group"],oracle_truth=row["truth"],checks=checks,mismatch=wrong,runs=val))
    path = ROOT / "logs" / (repo + ".jsonl.gz")
    data = "\n".join(json.dumps(row, separators=(",",":"), ensure_ascii=True) for row in out_rows) + "\n"
    path.write_bytes(gzip.compress(data.encode(), compresslevel=4, mtime=0))
    return repo, len(out_rows), sum(bool(r["mismatch"]) for r in out_rows), digest(path.read_bytes())


def main():
    groups = freeze()
    (ROOT / "logs").mkdir(exist_ok=True)
    start = time.perf_counter()
    report = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(work, g) for g in groups]
        for future in as_completed(jobs):
            r = future.result()
            report.append(r)
            print(*r[:3], flush=True)
    receipt = dict(repos=sorted(report), seconds=time.perf_counter()-start, python=sys.version,
                   machine=platform.platform(), git=subprocess.check_output(["git", "--version"], text=True).strip(),
                   sample_sha=digest((ROOT/"sample.lock.json").read_bytes()),
                   script_shas={s:digest((ROOT/s).read_bytes()) for s in ["lazy_git.py","run_audit.py"]})
    (ROOT/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf8")


if __name__ == "__main__":
    main()
