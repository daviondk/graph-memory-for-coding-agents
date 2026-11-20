"""Project cohort/phase identities without reading outcome or performance columns."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from download import ROOT, CACHE, pq

VERIFIED=("repo_only","raw_trace","summary_notes","structured_notes")
def dump(path,rs):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)

def run():
    source=json.loads((ROOT/"source.json").read_text(encoding="utf-8"))
    groups=defaultdict(dict)
    for d in source["files"]:
        p=CACHE/Path(d["key"]).name
        assert hashlib.sha256(p.read_bytes()).hexdigest()==d["sha256"]
        nonlabels=["run_id","subset","instance_id","initial_run_id","predecessor","successor","checkpoint_id","checkpoint_kind","handoff_view","attempt"]
        for r in pq.read_table(p,columns=nonlabels).to_pylist():
            if r["attempt"]!="r01":continue
            key=tuple(r[s] for s in nonlabels[1:8])
            assert r["handoff_view"] not in groups[key]
            groups[key][r["handoff_view"]]=r["run_id"]
    rows=[]
    for key,by in sorted(groups.items()):
        assert set(by)==set(VERIFIED)
        subset,iid,initial,pred,succ,cid,kind=key
        assert kind in ("post_failed_repair_edit","first_meaningful_modification","post_first_validation_result")
        rows.append({"subset":subset,"instance":iid,"initial":initial,"pred":pred,"succ":succ,"checkpoint":cid,"kind":kind,
                     "policy":"raw_trace" if kind=="post_failed_repair_edit" else "structured_notes",**by})
    assert len(rows)==1530
    dump(ROOT/"assignments.csv",rows)
    files=["PROTOCOL.md","design_lock.json","source.json","download.py","assign.py","assignments.csv"]
    (ROOT/"blind_lock.json").write_text(json.dumps({n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},indent=1),encoding="utf-8")
    print("cases locked",len(rows))
if __name__=="__main__":run()

