"""Assemble compact round-6 evidence from fixed branch outputs and verify all digests."""
import hashlib,json,os,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parent
B=R.parents[1];O=B/"outputs"
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def files():
    keep=set()
    for src in [R,*[R/k for k in ["version","retrieval","published","repair","repair/transfer","latency","report"]]]:
        keep.update(p for p in src.iterdir() if p.is_file() and p.suffix not in {".partial",".tmp"})
    for sub in ["version/external","version/codec","version/route","retrieval/author","retrieval/replication/encoder","repair/transfer/calls","report/pages","repair/calls","repair/oracle_calls"]:
        keep.update(p for p in (R/sub).rglob("*") if p.is_file() and "__pycache__" not in p.parts and ".git" not in p.parts)
    for d in list((R/"repair/tasks").iterdir())+list((R/"repair/transfer/tasks").iterdir()):
        keep.update(p for p in d.iterdir() if p.is_file() and p.suffix not in {".tmp"} and p.name!="checkout.tar.gz")
        for d1 in ["grades","grades_v2"]:
            keep.update(p for p in (d/d1).glob("*") if p.is_file())
    keep.update(p for p in (R/"retrieval/replication").iterdir() if p.is_file() and p.suffix!=".parquet" and p.name not in {"cff.gz","cfr.gz"})
    keep.update([R.parent/"graph_memory_round4/writer/python_prior.bin",R.parent/"memory_session5/live/tokenizer.json",R/"report/final/qa.json"])
    for p in (O/"graph-memory-research-round6.pdf",O/"graph-memory-research-round6.docx",O/"graph-memory-research-round2.docx"):
        if p.is_file():keep.add(p)
    return sorted(keep)
def main():
    items=files(); dest=O/"graph-memory-round6-records.zip";temp=dest.with_suffix(".partial")
    manifest={}
    with zipfile.ZipFile(temp,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True) as z:
        for p in items:
            name=p.relative_to(B).as_posix();manifest[name]=sha(p)
            z.write(p,name,compress_type=zipfile.ZIP_STORED if p.suffix in {".gz",".zip",".docx",".pdf",".png"} else zipfile.ZIP_DEFLATED)
        z.writestr("MANIFEST.json",json.dumps(manifest,sort_keys=True,indent=1))
    with zipfile.ZipFile(temp) as z:
        assert z.testzip() is None
        checked=json.loads(z.read("MANIFEST.json"))
        assert len(z.namelist())==len(checked)+1
        for name,digest in checked.items():
            with z.open(name) as f:assert hashlib.file_digest(f,"sha256").hexdigest()==digest,name
    os.replace(temp,dest)
    rec={"utc":datetime.now(timezone.utc).isoformat(),"files":len(manifest),"bytes":dest.stat().st_size,"sha256":sha(dest),"verified":"all entries CRC and per-entry SHA-256"}
    (O/"graph-memory-round6-verification.json").write_text(json.dumps(rec,indent=1),encoding="utf8");print(rec)
if __name__=="__main__":main()



