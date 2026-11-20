"""Independent first-parent diffs and primitive recency/selection audit, including all evaluated events."""
import concurrent.futures
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import run


def pair_diff(args):
    root, a, b = args
    fields = run.git(root, "diff", "--no-ext-diff", "--no-renames", "--name-status", "-z", a, b, "--", "*.py").split(b"\0")
    assert fields.pop() == b"" and len(fields) % 2 == 0
    touch, delete = [], []
    for k, f in zip(fields[::2], fields[1::2]):
        nf = f.decode("utf-8", "surrogateescape")
        if nf.endswith(".py"):
            (delete if k == b"D" else touch).append(nf)
    return sorted(touch), delete


def audit(pin, mirror, rows):
    timeline = run.git(mirror, "rev-list", "--reverse", "--first-parent", pin["sha"]).decode().splitlines()
    actual = {}
    for r in rows:
        if r["repo"] == pin["repo"]:
            assert r["index"] not in actual
            actual[r["index"]] = r
    count, active, freq, last = 0, set(), Counter(), {}
    with concurrent.futures.ThreadPoolExecutor(6) as executor:
        jobs = ((mirror, a, b) for a,b in zip(timeline,timeline[1:]))
        for i,(touched, deleted) in enumerate(executor.map(pair_diff,jobs)):
            if 2 <= len(touched) <= 20:
                r = actual[i]
                assert r["sha"] == timeline[i+1] and r["parent"] == timeline[i]
                assert r["split"] == ("warmup" if i < (len(timeline)-1)//2 else "evaluation")
                anchor = touched[int(hashlib.sha256(f"{pin['repo']}:{i}".encode()).hexdigest(),16)%len(touched)]
                assert anchor == r["anchor"] and sorted(set(touched)-{anchor}) == r["targets"]
                possible = active - {anchor}
                assert list(sorted(active.intersection(r["targets"]))) == r["reachable"] and len(possible)==r["candidates"]
                assert sorted(possible, key=lambda f:(-last[f],-freq[f], f))[:5] == r["result"]["recency"]["top5"]
                for result in r["result"].values():
                    top = result["top5"]
                    assert len(top) == min(5,len(possible)) and set(top) <= possible and len(set(top)) == len(top)
                    assert result["hits"] == len(set(top).intersection(r["targets"]))
                    assert result["hit1"] == int(bool(top) and top[0] in r["targets"])
                count += 1
            else:
                assert i not in actual
            freq.update(touched)
            last.update(dict.fromkeys(touched, i))
            active.difference_update(deleted)
            active.update(touched)
    assert len(actual)==count
    return {"repo":pin["repo"],"all_parent_child_pairs":len(timeline)-1,"query_rows":count}


if __name__ == "__main__":
    results = {}
    for folder,pins,mirrors in [("run","pins.json",run.DEFAULT_MIRRORS),("transfer_run","transfer_pins.json",run.HERE/"transfer_mirrors")]:
        rows = [json.loads(line) for line in (run.HERE/folder/"predictions.jsonl").read_text().splitlines()]
        records = json.loads((run.HERE/pins).read_text(encoding="utf-8-sig"))
        results[folder] = [audit(p,mirrors/p["repo"],rows) for p in records if "sha" in p]
    (run.HERE/"verification.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
    print({k:sum(d["all_parent_child_pairs"] for d in details) for k,details in results.items()})
