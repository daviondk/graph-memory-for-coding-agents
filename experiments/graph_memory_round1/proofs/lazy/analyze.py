"""Aggregate actual lazy Git reads. No resampling or method selection."""
from collections import Counter
from pathlib import Path
import csv
import gzip
import hashlib
import json
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
METHODS = ("direct","one","short3","diverse","historical")
FIELDS = ("blob_objects","blob_bytes","providers_parsed","tree_objects","tree_bytes",
          "tree_entry_headers_seen","commit_objects","commit_bytes","module_lookups","module_cache_hits",
          "tree_cache_hits","blob_cache_hits","adjacency_cache_hits","path_probes","parse_failures")
HISTORY = ("history_rev_list_calls","history_rev_list_bytes","history_diff_calls",
           "history_diff_name_bytes","history_changed_paths_seen")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def aggregate(rows):
    groups = {}
    for method in METHODS:
        arms = [r["runs"] for r in rows]
        stages = {}
        for phase in ("write","read"):
            vals = [a[("direct_old" if phase=="write" else "direct_new")] if method=="direct"
                    else a[method][phase] for a in arms]
            counters = {k:sum(v["counts"].get(k,0) for v in vals) for k in FIELDS}
            counters.update({k:sum(v.get("history",{}).get(k,0) for v in vals) for k in HISTORY})
            counters.update(seconds_total=sum(v["seconds"] for v in vals),
                            seconds_median=statistics.median(v["seconds"] for v in vals),
                            reads_zero=sum(v["counts"].get("blob_objects",0)==0 for v in vals),
                            truth_fast=sum(v.get("fast",False) for v in vals),
                            truth_verified=sum(v.get("validated",False) for v in vals))
            stages[phase] = counters
        stages["blob_total"] = sum(v["blob_objects"] for v in stages.values())
        stages["n"] = len(rows)
        if method != "direct":
            certs = [len(json.dumps(a[method]["certificate"],separators=(",",":")).encode()) for a in arms]
            stages["cache_bytes_total"] = sum(certs)
        groups[method] = stages
    return groups


def main():
    receipt = json.loads((ROOT/"receipt.json").read_text(encoding="utf8"))
    rows=[]
    for repo, count, errors, expected in receipt["repos"]:
        raw=(ROOT/"logs"/(repo+".jsonl.gz")).read_bytes()
        assert sha(raw)==expected
        records=[json.loads(line) for line in gzip.decompress(raw).splitlines()]
        assert len(records)==count and sum(bool(r["mismatch"]) for r in records)==errors
        rows += records
    sums = {**{g:aggregate([r for r in rows if r["group"]==g]) for g in ("A","B")},
            "all":aggregate(rows)}
    per_repo = {r:aggregate([x for x in rows if x["key"][0]==r]) for r in sorted({x["key"][0] for x in rows})}
    summary = {"n":len(rows),"repos":len(per_repo),"negative_new":sum(not r["oracle_truth"] for r in rows),
               "errors":sum(bool(r["mismatch"]) for r in rows),"groups":sums,"by_repo":per_repo,
               "runtime_seconds":receipt["seconds"]}
    (ROOT/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    with (ROOT/"costs.csv").open("w",encoding="utf8",newline="") as stream:
        cols=["repo","group","before","after","source","target","truth","method","phase",*FIELDS,*HISTORY,"seconds"]
        writer=csv.DictWriter(stream,cols)
        writer.writeheader()
        for row in rows:
            repo,before,after,s,t=row["key"]
            for method in METHODS:
                for phase in ("write","read"):
                    val = row["runs"][("direct_old" if phase=="write" else "direct_new")] if method=="direct" else row["runs"][method][phase]
                    writer.writerow(dict(repo=repo,group=row["group"],before=before,after=after,source=s,target=t,
                        truth=row["oracle_truth"],method=method,phase=phase,seconds=val["seconds"],
                        **{k:val["counts"].get(k,0) for k in FIELDS},
                        **{k:val.get("history",{}).get(k,0) for k in HISTORY}))
    print({k:summary[k] for k in ("n","repos","negative_new","errors","runtime_seconds")})
    for name,d in sums["all"].items():
        print(name, *(d[phase][metric] for phase in ("write","read") for metric in
              ("blob_objects","blob_bytes","tree_objects","tree_bytes","seconds_total","truth_fast","truth_verified","history_diff_calls")), d["blob_total"])
    for group in ("A","B"):
        print(group,{name:[d[p]["blob_objects"] for p in ("write","read")] for name,d in sums[group].items()})


if __name__=="__main__":
    main()
