"""Publish a compact archive of round-two protocols, predictions, scoring receipts and shared rerun inputs."""
import hashlib, json, zipfile, os
from pathlib import Path
R=Path(__file__).resolve().parent
BASE=R.parents[1]
OUT=BASE/"outputs"
def include_files():
    keep=set()
    def keep_file(f):
        if f.is_file() and not f.is_symlink() and "__pycache__" not in f.parts and f.suffix not in {".pyc",".tmp"}:keep.add(f)
    for p in R.glob("*"):keep_file(p)
    for component in ["attempt_memory","literature","failure_policy","edit_memory","span_memory"]:
        for p in (R/component).rglob("*"):keep_file(p)
    for component in ["multihop","localization","report"]:
        for p in (R/component).glob("*"):keep_file(p)
    for component in ["grounding","sensitivity300","orca_transfer"]:
        for p in (R/"localization"/component).glob("*"):keep_file(p)
    for p in (R/"report/pages").glob("*"):keep_file(p)
    for n in ('qa.json','numeric_audit.json','released.json'):keep_file(R/'report/final'/n)
    P=BASE/"work/memory_session5/packets"
    for n in ("common.py","policy.py","pipeline.py","extract5.py","parent_extract.py","qwen_tokenizer.json","shards.json","selection.json","transfer/selection.json","REPRODUCE.md"):
        keep_file(P/n)
    for p in P.glob("source/*/*.jsonl.gz"):keep_file(p)
    for p in P.glob("transfer/source/*.jsonl.gz"):keep_file(p)
    pre=BASE/"work/memory_session6/repair"
    for n in ("runner.py","worker.py","common.py","mbppplus.jsonl.gz","upstream-sanitized-mbpp.json","roster.json","cap1024/roster.json"):
        keep_file(pre/n)
    for i in json.loads((R/"attempt_memory/input_lock.json").read_bytes())["old_ids"]:
        for branch in ("current","raw","note"):
            src=pre/f"tasks/{i}/{branch}.json"
            key=json.loads(src.read_bytes())["call"];keep_file(src);keep_file(pre/f"tasks/{i}/{branch}.py")
            keep_file(pre/f"cap1024/programs/{key}.py")
    return sorted(keep)
def build():
    dest=OUT/"graph-memory-round2-records.zip"; partial=dest.with_suffix(".partial.zip")
    files={}
    with zipfile.ZipFile(partial,"w",zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for f in include_files():
            data=f.read_bytes();name=f.relative_to(BASE).as_posix()
            files[name]={"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()};z.writestr(name,data)
        z.writestr("MANIFEST.json",json.dumps({"format":1,"files":files},ensure_ascii=False,indent=1))
    with zipfile.ZipFile(partial) as z:
        assert z.testzip() is None
        assert set(z.namelist())==set(files)|{"MANIFEST.json"}
        for name,rec in files.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==rec["sha256"]
    os.replace(partial,dest)
    print(dest,len(files),dest.stat().st_size,hashlib.sha256(dest.read_bytes()).hexdigest())
if __name__=="__main__":build()

