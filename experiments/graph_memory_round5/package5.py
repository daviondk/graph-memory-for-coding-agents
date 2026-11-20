"""Inventory and verify experiment artifacts, reusing round four's streaming ZIP writer."""
import importlib.util,sys,hashlib,json,os,shutil
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parent;B=R.parents[1];O=B/"outputs";P=R.parent/"graph_memory_round4"
spec=importlib.util.spec_from_file_location("prior_archive",P/"package_round4.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
sha=module.sha
SKIP={"__pycache__","parser_lib","vendor","uv_cache","eval_deps","temp","final","env","lib",".uvcache",".venv","cache","blobs","snapshots","refs","wheels"}
def files():
    keep=set()
    for parent,dirs,names in os.walk(R):
        root=Path(parent);dirs[:]=[n for n in dirs if n not in SKIP and not (root/n).is_symlink()]
        for n in names:
            p=root/n
            if p.is_symlink() or p.suffix.lower() in {".pyc",".pyd",".dll",".exe",".tmp",".part",".gguf"}:continue
            keep.add(p)
    for p in [R/"report/final/qa.json",R/"report/final/crosschecks.json",O/"graph-memory-research-round5.docx",O/"graph-memory-research-round5.pdf",O/"graph-memory-research-round2.docx",P/"package_round4.py"]: 
        if p.is_file():keep.add(p)
    for sub in ["data_io.py","memory.py","archive_members.json","archive_convert.py","archive_probe.py","archive_audit.json","archive.pred.jsonl.gz","full.pred.jsonl.gz","roster.json"]:
        if (P/"repo"/sub).is_file():keep.add(P/"repo"/sub)
    return sorted(keep)
def main():
    values=files()
    if "list" in sys.argv:print(len(values),sum(p.stat().st_size for p in values)/1048576);return
    dest=O/"graph-memory-round5-records.zip";tmp=dest.with_suffix(".partial")
    manifest=module.create(B,values,tmp)
    os.replace(tmp,dest)
    rec=dict(utc=datetime.now(timezone.utc).isoformat(),members=len(manifest["files"]),bytes=dest.stat().st_size,sha256=sha(dest),verified="ZIP CRC + per-member SHA-256",documents={f:sha(O/f) for f in ["graph-memory-research-round5.docx","graph-memory-research-round5.pdf"]})
    (O/"graph-memory-round5-verification.json").write_text(json.dumps(rec,indent=2),encoding="utf8");print(rec)
if __name__=="__main__":main()

