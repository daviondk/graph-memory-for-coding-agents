"""Reconstruct only the pre-human E4 sample with the upstream sampler and local score envelopes."""
import collections
import gzip
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parent.parent
UP=Path(os.environ.get("GRAPHMEMORY_REPO","D:/CodexResearch/x20-isetrace-runtime/upstream"))
meta=Path(os.environ.get("ISETRACE_QUERY_METADATA","D:/CodexResearch/x20-isetrace-runtime/inputs/query-authoring/isetrace-v7-raw.jsonl.metadata.jsonl"))
sys.path.insert(0,str(UP))
spec=importlib.util.spec_from_file_location("native_e4",UP/"scripts/e4/audit_isetrace_e4.py")
native=importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
def read(p):
    return json.loads(gzip.decompress(p.read_bytes()))
def main():
    assert subprocess.check_output(["git","-C",str(UP),"rev-parse","HEAD"],text=True).strip()=="df29287116fa1565b3fd6b485022cd6090dc0b27"
    split=read(BASE/"graph_memory_round19/trained_rank/split.json.gz")
    test={r["q"]:r["t"] for r in split["test"]}
    md=[json.loads(line) for line in meta.read_bytes().splitlines()]
    fields=sorted(set().union(*(r.keys() for r in md)))
    modes={r["query_id"]:r["memory_mode"] for r in md if r["query_id"] in test}
    assert set(test)==set(modes) and len(test)==2000
    assert all(r["trajectory_id"]==test[r["query_id"]] for r in md if r["query_id"] in test)
    ids=native._stratified_sample(modes_by_id=modes,sample_size=native.DEFAULT_SAMPLE_SIZE,seed=native.DEFAULT_SAMPLE_SEED)
    r18=read(BASE/"graph_memory_round18/isetrace_official/outcomes.json.gz")
    rows={}
    for r in r18:
        if r["arm"]=="prefix" and r["q"] in ids:
            rows.setdefault(r["view"]+"_bm25_prefix",{})[r["q"]]=(r["full_support"],r["coverage"])
    for r in read(BASE/"graph_memory_round19/trained_rank/table1-rows.json.gz"):
        if r["q"] in ids:
            rows.setdefault("local_pu_denseft_native_prefix",{})[r["q"]]=(r["full_support_2048"],r["coverage_2048"])
    assert len(rows)==3
    out={}
    for arm, vals in rows.items():
        assert set(vals)==ids
        x={}
        for j,metric in enumerate(("full_support","coverage")):
            sorted_values=sorted(z[j] for z in vals.values())
            x[metric]={"full_500":sum(sorted_values)/500,"unknown_469_lower":sum(sorted_values[:469])/469,
                       "unknown_469_upper":sum(sorted_values[-469:])/469}
        out[arm]=x
    result=dict(n=500,seed=native.DEFAULT_SAMPLE_SEED,md_rows=len(md),md_fields=fields,source_code=hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
            md_sha256=hashlib.sha256(meta.read_bytes()).hexdigest(),mode_counts=dict(collections.Counter(modes[k] for k in ids)),
            unique_trajectories=len({test[k] for k in ids}),queries=sorted(ids),statistics=out)
    (HERE/"e4-reconstruction.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8",newline="\n")
    print(result["mode_counts"],result["unique_trajectories"],out)
if __name__=="__main__":
    main()
