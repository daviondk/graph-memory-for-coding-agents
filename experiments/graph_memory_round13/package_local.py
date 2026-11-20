"""Create and recheck a portable ZIP of completed R13 small research records."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
MANIFEST="MANIFEST.sha256"
STUDIES=("reformulation","provenance","checkpoints","read_action")
PUBLIC_GRADES={"grade.py","score.py","report.py","grading.log","results.json","REPORT_RU.md","README_RU.md",
               "result.json","eval_stderr.log","eval_stdout.log","unit.log","container.log","native-report.json"}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def safe(name):
    path=PurePosixPath(name)
    return path.as_posix()==name and not path.is_absolute() and all(not s.startswith(".") and
        not any(c in s for c in ':\\<>*|?"') for s in path.parts)

def load(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix==".gz" else data)

def selected():
    names={"REPORT_RU.md","REPRODUCE_RU.md","RELATED_WORK_RU.md","SLIDES_SOURCE_RU.md","package_local.py"}
    for s in ("reformulation","provenance"):
        folder=ROOT/s; idx=folder/"MANIFEST_SHA256.json"; names.add(idx.relative_to(ROOT).as_posix())
        for name,h in load(idx).items():
            assert safe(name)
            src=folder/name
            assert digest(src.read_bytes())==h and src.resolve().is_relative_to(folder.resolve())
            names.add(src.relative_to(ROOT).as_posix())
    for study in ("read_action","checkpoints"):
        folder=ROOT/study
        for src in folder.rglob("*"):
            if not src.is_file():continue
            r=src.relative_to(folder)
            if any(s.startswith(".") or s=="__pycache__" for s in r.parts):continue
            if len(r.parts)==1 and src.suffix in {".md",".json",".jsonl",".py",".gz",".log"}:pass
            elif study=="checkpoints" and r.parts[0]=="patches" and len(r.parts)==2 and src.name.endswith(".patch.gz"):
                assert digest(gzip.decompress(src.read_bytes()))==src.name.split(".")[0]
            elif study=="checkpoints" and r.parts[0]=="grading" and src.name in PUBLIC_GRADES:pass
            else:continue
            names.add(src.relative_to(ROOT).as_posix())
    needed={"reformulation/REPORT_RU.md","provenance/REPORT_RU.md","read_action/REPORT_RU.md","checkpoints/REPORT_RU.md"}
    assert needed<=names, needed-names
    actions=load(ROOT/"read_action/results.json")
    assert set(actions)=={"main","external"}
    for name,h in load(ROOT/"read_action/action-lock.json").items():assert digest((ROOT/"read_action"/name).read_bytes())==h
    grade=load(ROOT/"checkpoints/grading/results.json")
    assert grade["complete"] and len(grade["rows"])==4
    assert all(safe(n) for n in names) and len(names)==len({n.casefold() for n in names})
    return sorted(names)

def verify(z):
    names=z.namelist(); assert len(names)==len(set(names)) and all(safe(n) for n in names)
    records=dict(line.split("  ",1)[::-1] for line in z.read(MANIFEST).decode().splitlines())
    assert set(records)==set(names)-{MANIFEST}
    for name,h in records.items():assert digest(z.read(name))==h
    return records

def run(out,export):
    assert not out.exists() and not out.resolve().is_relative_to(ROOT.resolve())
    files=selected(); pairs={n:digest((ROOT/n).read_bytes()) for n in files}
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as t:
        temp=Path(t)/"records.zip"
        with zipfile.ZipFile(temp,"w") as z:
            for name in files+[MANIFEST]:
                b=((ROOT/name).read_bytes() if name!=MANIFEST else "".join(h+"  "+n+"\n" for n,h in pairs.items()).encode())
                zi=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));zi.external_attr=0o100644<<16
                z.writestr(zi,b,compress_type=zipfile.ZIP_STORED if name.endswith(".gz") else zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(temp) as z:assert verify(z)==pairs
        assert all(digest((ROOT/k).read_bytes())==v for k,v in pairs.items())
        os.link(temp,out)
    if export:
        assert not export.exists() and not export.resolve().is_relative_to(ROOT.resolve())
        with tempfile.TemporaryDirectory(dir=export.parent) as t:
            stage=Path(t)/"records";stage.mkdir()
            with zipfile.ZipFile(out) as z:
                verify(z)
                for name in z.namelist():
                    dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
            assert all(digest((stage/n).read_bytes())==h for n,h in pairs.items())
            stage.rename(export)
    print(len(pairs),digest(out.read_bytes()),out)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("archive",type=Path)
    parser.add_argument("--verify",action="store_true")
    parser.add_argument("--export",type=Path)
    args=parser.parse_args()
    if args.verify:
        with zipfile.ZipFile(args.archive) as z:print(len(verify(z)),digest(args.archive.read_bytes()))
    else:run(args.archive,args.export)
