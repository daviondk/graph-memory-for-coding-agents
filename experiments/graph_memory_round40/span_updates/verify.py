"""Offline paired validation of exact results, scope, and raw-file audit lineage."""
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean
from collections import defaultdict

ROOT=Path(__file__).resolve().parent


def read(name):
    data=(ROOT/name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def calculate():
    rows=read("scored.json.gz")
    strict={(rid,at):v for rid,at,v in read("audit_strict_rows.json.gz")}
    assert len(rows)==len(strict)==2696
    out={}
    for mode in ("main","additional","all"):
        group=rows if mode=="all" else [r for r in rows if r["group"]==mode]
        checks=[strict[(r["rid"],r["receipt"])] for r in group]
        valid=[bool(r["range_reuse"] and not c.get("reused_selected_post_mismatch",0)) for r,c in zip(group,checks)]
        by_issue=defaultdict(list)
        for r,hit in zip(group,valid):
            by_issue[r["issue"]].append(int(hit)-r["file_reuse"])
        base=read("results.json")["groups"][mode]
        assert len(group)==base["n"] and sum(x["range_reuse"] for x in group)==base["range_reuse"]
        assert all(c.get("new_mismatch",0)==0 for c in checks)
        out[mode]=dict(n=len(group), old_file=base["file_reuse"], stable_id=base["range_reuse"], checked_reuse=sum(valid),
                issues=len(by_issue), macro_checked_pp=100*mean(mean(values) for values in by_issue.values()),
                changed_text_on_reused=sum(bool(c.get("reused_selected_post_mismatch",0)) for c in checks),
                selected_lines=sum(c.get("reused_selected_lines",0) for c in checks),
                stale_lines=sum(c.get("reused_selected_post_mismatch",0) for c in checks),
                with_source_lines=sum(r["range_reuse"]==1 and c.get("reused_selected_lines",0)>0 for r,c in zip(group,checks)))
    return out


if __name__=="__main__":
    expected=ROOT/"strict_summary.json"
    observed=calculate()
    if expected.exists():
        assert observed==read("strict_summary.json")
    print(json.dumps(observed,indent=2))

