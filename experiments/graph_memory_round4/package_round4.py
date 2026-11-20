"""Build and verify the round-four research archive. `inventory` and `self-test` never publish a release."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROUND = Path(__file__).resolve().parent
BASE = ROUND.parents[1]
OUTPUT = BASE / "outputs"
LABEL = "graph-memory-round4"
TITLE = "graph-memory-research-round4"
ARCHIVE = OUTPUT / (LABEL + "-records.zip")
BRANCHES = ("action","encoder","java_long","java_reader","repair","repo","writer","report")
IGNORED_DIRS = {"__pycache__", ".git", ".venv", "site-packages", "node_modules",
                "cache","strict_cache","toolcache",".scratch",".uvcache",".uv-cache","lib","tmp","temp"}
FORMATS = {".py",".ps1",".md",".txt",".json",".jsonl",".gz",".log",".csv",".tsv",
           ".rst",".yaml",".yml",".toml",".bib",".npz",".npy",".pkl",".png",".svg",
           ".jpg",".webp",".stdout",".stderr",".parquet",".pdf",".docx",".pyi"}

def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def file_set():
    found = set()
    def add(p):
        if p.is_file() and not p.is_symlink():
            if not p.resolve().is_relative_to(BASE):
                raise ValueError(f"Outside workspace: {p}")
            found.add(p)
    def relative(folder, *names):
        for n in names:
            add(folder/n)
    def globset(folder, *patterns):
        for pattern in patterns:
            for p in folder.glob(pattern):
                add(p)
    for branch in BRANCHES:
        folder=ROUND/branch
        for parent,dirs,names in os.walk(folder, followlinks=False):
            at=Path(parent); rel=at.relative_to(folder)
            dirs[:]=[n for n in dirs if n not in IGNORED_DIRS and not (at/n).is_symlink()]
            if branch=="encoder":
                dirs[:]=[n for n in dirs if n.lower() not in {"model","models","weights","download","downloads","downloaded","env","venv","venv312","native","hub","inputs","blobs","snapshots","refs","artifacts","environment","huggingface","hf-cache","__pypackages__"} and not n.startswith("models--")]
            if branch=="repo" and not rel.parts:
                dirs[:]=[n for n in dirs if n not in {"inputs","archive_inputs","legacy_check","protocol_cache","tokenizer_snapshot","native","native_holdout"}]
            if branch=="report" and not rel.parts:
                dirs[:]=[n for n in dirs if n!="final"]
            for name in names:
                p=at/name
                if name.startswith("~$") or p.suffix.lower() in {".tmp",".part",".pyc",".zip",".gguf",".exe",".dll",".pyd",".bak"}: continue
                if p.suffix.lower() in FORMATS or (branch=="writer" and name=="python_prior.bin"):
                    add(p)
    # Author-run native search receipts stay useful without redistributing its executable, model cache or indexes.
    globset(ROUND/"repo/native","*.log","*.json")
    globset(ROUND/"repo/native_holdout","*/*.log","*/*.json")
    globset(ROUND/"report/final","*.json")
    for p in ROUND.iterdir():
        if p.is_file() and p.suffix.lower() in FORMATS:
            add(p)
    relative(OUTPUT,"graph-memory-research-round2.docx",TITLE+".pdf",TITLE+".docx")
    r3=BASE/"work/graph_memory_round3"; r2=BASE/"work/graph_memory_round2"
    p5=BASE/"work/memory_session5/packets"
    relative(r3/"context","context.py")
    relative(r3/"serialized_writer","writer.py","method_lock.json")
    relative(r3/"context","acquire.py","confirm_acquire.py")
    for name in ("real_swe","real_swe_followup"):
        ds=r3/name
        globset(ds,"*.py","source_*.gz","events_*.gz","*receipt*.json",
                "selection.json","download_summary.json","metadata_audit.json","method_lock.json","PROTOCOL_RU.md")
    relative(r3/"real_swe","official_verified.parquet")
    globset(r3/"demand","source_*.gz","selection.json","acquisition.json")
    relative(r3/"repo","fetch.py","sources.json","REPRODUCE.md","requirements.txt")
    relative(r3/"repo/inputs","codegen_tokenizer.json")
    relative(r2/"edit_memory","experiment.py","model.json","split.json")
    relative(r2/"span_memory","run.py","width_model.json","offset.json","budget.py","selection.json")
    relative(p5,"common.py","policy.py","pipeline.py","extract5.py","parent_extract.py","qwen_tokenizer.json","shards.json")
    globset(p5/"source/train","*.gz")
    relative(BASE/"work/memory_session5/live","tokenizer.json","roster.json","transfer/roster.json")
    return sorted(found)

def safe_name(name):
    p=PurePosixPath(name)
    return (name==p.as_posix() and not p.is_absolute() and not any(s in {".","..",""} for s in p.parts)
            and "\\" not in name and ":" not in name)

def verify(source):
    with ZipFile(source) as z:
        if z.testzip() is not None:raise ValueError("ZIP CRC check failed")
        manifest=json.loads(z.read("MANIFEST.json"))
        records=manifest["files"]
        names=z.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(records)|{"MANIFEST.json"}:
            raise ValueError("Unexpected or duplicated ZIP member")
        for n,rec in records.items():
            if not safe_name(n) or z.getinfo(n).file_size!=rec["bytes"]:
                raise ValueError(f"Invalid path or length: {n}")
            with z.open(n) as stream:
                if hashlib.file_digest(stream,"sha256").hexdigest()!=rec["sha256"]:
                    raise ValueError(f"Digest mismatch: {n}")
    return manifest

def create(root,files,destination):
    manifest={}
    with ZipFile(destination,"w",ZIP_DEFLATED,compresslevel=5,allowZip64=True) as z:
        for p in files:
            n=p.relative_to(root).as_posix()
            if not safe_name(n) or n in manifest:raise ValueError(n)
            # Hash exactly the bytes that were archived, while detecting files changing mid-copy.
            prior=p.stat(); info=ZipInfo.from_file(p,n);info.compress_type=ZIP_DEFLATED
            h=hashlib.sha256();size=0
            with p.open("rb") as src,z.open(info,"w") as out:
                while block:=src.read(1024*1024):
                    out.write(block);h.update(block);size+=len(block)
            after=p.stat()
            if prior.st_size!=size or (after.st_size,after.st_mtime_ns)!=(prior.st_size,prior.st_mtime_ns):
                raise RuntimeError(f"File changed while packaging: {p}")
            manifest[n]={"bytes":size,"sha256":h.hexdigest()}
        data={"format":1,"algorithm":"sha256","files":manifest}
        z.writestr("MANIFEST.json",json.dumps(data,ensure_ascii=True,indent=1))
    return verify(destination)

def self_test():
    # Only an invented two-file project, with a second ZIP containing a deliberately wrong hash.
    with tempfile.TemporaryDirectory(prefix="round4-pack-test-",dir=BASE/"work") as temp:
        test=Path(temp).resolve()
        assert test.parent==(BASE/"work").resolve() and test.name.startswith("round4-pack-test-")
        example=test/"fixture";example.mkdir()
        sub=example/"sub";sub.mkdir()
        (example/"first.txt").write_bytes(b"abc"); (sub/"empty.txt").write_bytes(b"")
        files=[example/"first.txt",sub/"empty.txt"]
        good=create(example,files,test/"fixture.zip")
        assert len(good["files"])==2 and good["files"]["sub/empty.txt"]["bytes"]==0
        good["files"]["first.txt"]["sha256"]="0"*64
        broken=test/"wrong.zip"
        with ZipFile(broken,"w") as z:
            for f in files:z.write(f,f.relative_to(example).as_posix())
            z.writestr("MANIFEST.json",json.dumps(good))
        try:verify(broken)
        except ValueError as err:assert "Digest mismatch" in str(err)
        else:raise AssertionError("Wrong digest was accepted")
        assert not any(safe_name(n) for n in ["../x","/y","C:/file","bad\\file","a/../b","a//b"])
    print("Synthetic ZIP passed byte-identity, empty file, membership, path and corruption checks.")

def publish():
    files=file_set()
    for ext in ("docx","pdf"):
        public=OUTPUT/(TITLE+"."+ext)
        if not public.is_file():raise FileNotFoundError(public)
        rendered=ROUND/"report/final"/public.name
        if not rendered.is_file() or sha(rendered)!=sha(public):raise ValueError(f"Report is not the rendered release: {public}")
    if not (ROUND/"report/final/qa.json").is_file():raise FileNotFoundError("report/final/qa.json")
    OUTPUT.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=LABEL+"-",suffix=".partial.zip",dir=OUTPUT,delete=False) as named:
        temp=Path(named.name)
    try:
        manifest=create(BASE,files,temp)
        os.replace(temp,ARCHIVE)
    finally:
        temp.unlink(missing_ok=True)
    receipt=dict(file=ARCHIVE.name,bytes=ARCHIVE.stat().st_size,sha256=sha(ARCHIVE),
                 count=len(manifest["files"]),uncompressed_bytes=sum(r["bytes"] for r in manifest["files"].values()),
                 reports={ext:sha(OUTPUT/(TITLE+"."+ext)) for ext in ("docx","pdf")})
    (OUTPUT/(LABEL+"-verification.json")).write_text(json.dumps(receipt,indent=2),encoding="utf8")
    print(json.dumps(receipt))

def replay():
    verify(ARCHIVE)
    with tempfile.TemporaryDirectory(prefix="round4-replay-",dir=BASE/"work") as temp:
        root=Path(temp).resolve();assert root.parent==(BASE/"work").resolve() and root.name.startswith("round4-replay-")
        with ZipFile(ARCHIVE) as z:z.extractall(root)
        action=root/"work/graph_memory_round4/action"
        old=json.loads((action/"wire_audit.json").read_bytes())
        env=dict(os.environ,PYTHONIOENCODING="utf8",PYTHONPATH="")
        subprocess.run([sys.executable,"verify.py"],cwd=action,check=True,env=env,timeout=240)
        assert json.loads((action/"wire_audit.json").read_bytes())==old
        long=root/"work/graph_memory_round4/java_long"
        if (long/"long_audit.json").is_file():
            reference=json.loads((long/"long_audit.json").read_bytes())
            subprocess.run([sys.executable,"audit.py"],cwd=long,check=True,env=env,timeout=90)
            assert json.loads((long/"long_audit.json").read_bytes())==reference
        report=root/"work/graph_memory_round4/report"
        if (report/"numeric_audit.py").is_file():
            (report/"final").mkdir(exist_ok=True)
            before=report/"final/numeric_audit.json"
            old_audit=json.loads(before.read_bytes()) if before.exists() else None
            subprocess.run([sys.executable,"numeric_audit.py"],cwd=report,check=True,env=env,timeout=120)
            if old_audit is not None:assert json.loads(before.read_bytes())==old_audit
    path=OUTPUT/(LABEL+"-verification.json")
    if path.exists():
        receipt=json.loads(path.read_bytes());receipt["fresh_extraction_action_audit"]=True
        path.write_text(json.dumps(receipt,indent=2),encoding="utf8")
    print("Fresh extraction passed.")

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("command",choices=("inventory","self-test","publish","verify","replay"));args=cli.parse_args()
    if args.command=="inventory":
        files=file_set();groups=Counter()
        for p in files:
            seg=p.relative_to(BASE).parts
            k="/".join(seg[:3]) if seg[:2]==("work",ROUND.name) else "/".join(seg[:2])
            groups[k]+=p.stat().st_size
        print(json.dumps({"files":len(files),"bytes_by_directory":groups},indent=1))
    elif args.command=="self-test":self_test()
    elif args.command=="publish":publish()
    elif args.command=="verify":print("Verified files:",len(verify(ARCHIVE)["files"]))
    else:replay()
if __name__=="__main__":main()
