"""Evaluate a sealed routing policy after excluding verbatim train/dev source repeats."""
import json
import sys

from gate import ROOT, R19, load, put, sha
from evaluate import contrast

R19_AUDIT = R19 / "split_overlap"
sys.path.insert(0, str(R19_AUDIT))
from audit import QUERY, authoring_fields


def partition():
    # Both CPU routes are already predicted; raw query-authoring records contain references.
    assert all((ROOT/f"{tag}-decision-seal.json").exists() for tag in ("hash64","availability"))
    split = load(R19/"trained_rank/split.json.gz")
    dev = {v["q"] for v in split["dev"]}
    targets = {v["q"] for v in split["test"]}
    assert len(dev) == 500 and len(targets) == 2000 and not dev & targets
    dev_sources = set()
    test_sources = {}
    raw_hash = sha(QUERY)
    previous = load(R19_AUDIT/"overlap-lock.json")
    assert previous["inputs"][str(QUERY)] == raw_hash
    with QUERY.open(encoding="utf8") as f:
        for line in f:
            rec = json.loads(line)
            q = rec["id"]
            if q in dev or q in targets:
                sig = authoring_fields(rec)[0]
                if q in dev:
                    dev_sources.update(sig["sources"])
                else:
                    assert q not in test_sources
                    test_sources[q] = sig["gold_fields"]
    assert set(test_sources) == targets
    prior_file = R19_AUDIT/"overlap-flags.json.gz"
    assert sha(prior_file) == previous["flags"]
    dense = {x["q"]:x["gold_field"] for x in load(prior_file)
             if x["train"]=="dense" and x["split"]=="test"}
    assert set(dense) == targets and sum(dense.values()) == 125
    rows = [{"q":q, "dense_train":dense[q],"gate_dev":bool(dev_sources & test_sources[q])} for q in sorted(targets)]
    put(ROOT/"transfer-source-flags.json.gz",rows)
    put(ROOT/"transfer-source-receipt.json",{
        "raw_sha256":raw_hash, "r19_flags_sha256":sha(prior_file),
        "flags":sha(ROOT/"transfer-source-flags.json.gz"),
        "dev_ids":500,"test_ids":2000,"dev_field_match":sum(r["gate_dev"] for r in rows),
        "train_field_match":125,"both":sum(r["gate_dev"] and r["dense_train"] for r in rows),
    })
    return rows


def main():
    flags = partition()
    for tag in ("availability","hash64"):
        p = ROOT/f"{tag}-outcomes.json.gz"
        results = {r["q"]:r for r in load(p)}
        assert set(results) == {v["q"] for v in flags}
        summary = {}
        for kind in ("omit_dev_matches","omit_train_and_dev_matches"):
            keep = [results[v["q"]] for v in flags
                    if not v["gate_dev"] and (kind=="omit_dev_matches" or not v["dense_train"])]
            estimate = contrast(keep,"gate50","always_graph")
            fs_delta = estimate["metric"]["fs"]
            calls = sum(r["methods"]["gate50"]=="graph" for r in keep)
            summary[kind] = dict(n=len(keep),trajectories=estimate["tr"],calls=calls,
                gate=sum(r[r["methods"]["gate50"]]["fs"] for r in keep),
                graph=sum(r["graph"]["fs"] for r in keep),paired_fs=fs_delta,win=estimate["win"],loss=estimate["lose"],
                criterion=(fs_delta["ci"][0]>-.01 and calls/len(keep)<=.60))
        put(ROOT/f"{tag}-source-transfer.json",dict(outcomes=sha(p),
            flags=sha(ROOT/"transfer-source-flags.json.gz"),panels=summary))
        print(tag,summary,flush=True)


if __name__ == "__main__":
    main()
