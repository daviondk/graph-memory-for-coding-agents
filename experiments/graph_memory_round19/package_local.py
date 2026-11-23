"""Package and verify the studies of round 19."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
STUDIES=('online_write','write_transfer','write_learned','learned_mask','bounded_dense','trained_rank','tail_read','locomo_edges','writer_action','split_overlap','resource_memory','action_transfer')
def hash_file(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def safe(name):
    p=PurePosixPath(name)
    return p.as_posix()==name and not p.is_absolute() and all(not part.startswith(".") and not any(c in part for c in ':\\<>*|?"') for part in p.parts)
def snapshot():
    records={n:hash_file(ROOT/n) for n in ("REPORT_RU.md","REPRODUCE_RU.md","RELATED_WORK_RU.md","package_local.py","figure.py","write-read.png","stage_effects.py","stage-effects.json")}
    for study in STUDIES:
        d=ROOT/study;m=d/"MANIFEST_SHA256.json";items=json.loads(m.read_bytes())
        assert "REPORT_RU.md" in items
        records[study+"/"+m.name]=hash_file(m)
        for name,h in items.items():
            assert safe(name) and name!=m.name
            src=d/name
            assert src.resolve().is_relative_to(d.resolve()) and src.stat().st_size<64*1024**2
            assert hash_file(src)==h, src
            records[study+"/"+name]=h
    return dict(sorted(records.items()))
def audit(z):
    names=z.namelist()
    assert all(safe(n) for n in names) and len(names)==len({n.casefold() for n in names})
    records={n:h for h,n in (l.split("  ",1) for l in z.read("MANIFEST.sha256").decode().splitlines())}
    assert set(names)==set(records)|{"MANIFEST.sha256"}
    for k,v in records.items():assert hashlib.sha256(z.read(k)).hexdigest()==v
    for study in STUDIES:
        m=study+"/MANIFEST_SHA256.json"
        expected=json.loads(z.read(m))
        assert {s for s in records if s.startswith(study+"/")}=={m,*[study+"/"+n for n in expected]}
        assert all(records[study+"/"+n]==h for n,h in expected.items())
    return records
def build(out,export):
    assert not out.exists() and not out.resolve().is_relative_to(ROOT.resolve())
    records=snapshot();man="".join(h+"  "+k+"\n" for k,h in records.items()).encode()
    with tempfile.TemporaryDirectory(dir=out.parent) as t:
        stage=Path(t)/"staged.zip"
        with zipfile.ZipFile(stage,"w") as z:
            for name in [*records,"MANIFEST.sha256"]:
                info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.external_attr=0o100644<<16
                z.writestr(info,man if name=="MANIFEST.sha256" else (ROOT/name).read_bytes(),compress_type=zipfile.ZIP_STORED if name.endswith(".gz") else zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(stage) as z:assert audit(z)==records
        assert snapshot()==records
        os.link(stage,out)
    if export:
        assert not export.exists() and not export.resolve().is_relative_to(ROOT.resolve())
        with tempfile.TemporaryDirectory(dir=export.parent) as t:
            root=Path(t)/"staged";root.mkdir()
            with zipfile.ZipFile(out) as z:
                audit(z)
                for n in z.namelist():
                    p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(n))
            assert all(hash_file(root/n)==h for n,h in records.items())
            root.rename(export)
    print(len(records),hash_file(out),out)
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("zip",type=Path);parser.add_argument("--verify",action="store_true");parser.add_argument("--export",type=Path)
    args=parser.parse_args()
    if args.verify:
        with zipfile.ZipFile(args.zip) as z:print(len(audit(z)),hash_file(args.zip))
    else:build(args.zip,args.export)
