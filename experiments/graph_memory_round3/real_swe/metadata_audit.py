"""Confirm identity of the selected issue, repository, base revision and initial request against the publisher."""
import hashlib,json,sys,urllib.request
from pathlib import Path
D=Path(__file__).resolve().parent;P=D.parents[1]/"memory_session5/packets";sys.path.insert(0,str(P))
from extract5 import pq
REV="78f471bf655a3137b2e8a75af1501690ec009ec3";EXPECTED="030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25"
url="https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/resolve/"+REV+"/data/test-00000-of-00001.parquet"
dest=D/"official_verified.parquet"
if not dest.exists():
    with urllib.request.urlopen(url,timeout=45) as f:dest.write_bytes(f.read())
assert hashlib.sha256(dest.read_bytes()).hexdigest()==EXPECTED
col=["instance_id","repo","base_commit","problem_statement"]
known={r["instance_id"]:r for r in pq.read_table(dest,columns=col).to_pylist()}
selected=json.loads((D/"selection.json").read_bytes());out={"publisher_url":url,"publisher_sha256":EXPECTED,"official_rows":len(known),"selected":len(selected),"exact_matches":{}}
for name in col:
    out["exact_matches"][name]=sum(r[name]==known[r["instance_id"]][name] for r in selected)
out["mismatched_ids"]=[r["instance_id"] for r in selected if r!=known[r["instance_id"]]]
(D/"metadata_audit.json").write_text(json.dumps(out,indent=1));print(out["exact_matches"],len(out["mismatched_ids"]))

