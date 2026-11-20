"""Call the unchanged official per-target pipeline and capture observed method costs."""
import argparse
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from fetch_history import BASE, META

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/"scripts"))
import run_memory as official
from methods import METHODS, MAX_WORDS, MAX_CHARS

FOCUS_IDS=("brazilian-utils__brutils-python-125","s-knibbs__dataclasses-jsonschema-64")


def run_task(arg):
    target,method=arg
    q=target["instance_id"]
    repo=target["repo"].replace("/","__")
    ready=META/(repo+".ready.json")
    if not ready.exists():
        raise RuntimeError("Repository histories incompletely fetched: "+repo)
    status=BASE/"memory-stage-audit"/method/(q+".json")
    if status.exists():
        return
    impl=METHODS[method]()
    result=official.run_one(target,method=method,memory_factory=lambda:impl,top_k=1,
        out_root=BASE/"outputs"/"memory",run_id="x20-vibe-frozen",max_session_mb=64.0,overwrite=True)
    assert result and result["num_retrieved"]<=1
    hashes=[]
    for item in result["retrieved"]:
        sid=item["source_session_id"]
        assert sid.rsplit("-",1)[0]==q.rsplit("-",1)[0] and int(sid.rsplit("-",1)[1])<int(q.rsplit("-",1)[1])
        content=item["content"]
        assert len(content.split())<=MAX_WORDS and len(content)<=MAX_CHARS
        hashes.append(hashlib.sha256(content.encode()).hexdigest())
    reader=(BASE/"outputs"/"memory"/method/target["language"]/q/"memory.txt").read_text(encoding="utf8")
    audit={"instance_id":q,"repo":target["repo"],"language":target["language"],"method":method,
           "source_histories": result["num_histories_fed"],"source_messages":result["num_messages_fed"],
           "skipped_sessions":len(result["skipped_sessions"]),"stored_records":impl.count(),
           "stored_text_bytes":impl.stored_bytes,"retrieved":result["num_retrieved"],"words_with_header":len(reader.split()),
           "chars_with_header":len(reader),"content_sha256":hashes[0] if hashes else None,"wall_seconds":result["elapsed_seconds"],
           "selected_source":result["retrieved"][0]["source_session_id"] if hashes else None,
           "selected_kind":result["retrieved"][0]["metadata"].get("evidence_kind") if hashes else None}
    if hasattr(impl,"kinds"):
        audit["stored_by_kind"]=dict(impl.kinds)
    status.parent.mkdir(exist_ok=True,parents=True)
    status.write_text(json.dumps(audit),encoding="utf8")
    print(method,q,result["num_histories_fed"],result["num_retrieved"],flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--focus",action="store_true")
    p.add_argument("--ready",action="store_true")
    p.add_argument("--workers",type=int,default=4)
    p.add_argument("--methods",nargs="+",choices=list(METHODS),default=list(METHODS))
    a=p.parse_args()
    targets=official.load_targets()
    if a.focus:
        targets=[t for t in targets if t["instance_id"] in FOCUS_IDS]
    if a.ready:
        targets=[t for t in targets if (META/(t["repo"].replace("/","__")+".ready.json")).exists()]
    # Per-process constructors and workers never share a target's memory state.
    args=[(t,m) for t in targets for m in a.methods]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        list(pool.map(run_task,args))
