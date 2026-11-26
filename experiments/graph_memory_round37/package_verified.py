"""Create a relocatable, verified snapshot of completed experiments."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile
from verify import verify

ROOT=Path(__file__).resolve().parent
STUDIES=tuple(json.loads((ROOT/"release.json").read_bytes())["completed"])
TOP=("REPORT_RU.md","release.json","verify.py","package_verified.py","native_registration/plan.json","native_registration/PROTOCOL_RU.md")
ALLOWED={".db",".css",".js",".pdf",".sqlite3",".npz",".cpp",".ps1",".mjs",".html",".png",".py",".md",".json",".gz",".sqlite"}

def digest(b):return hashlib.sha256(b).hexdigest()
def snapshot():
    verify()
    files={n:digest((ROOT/n).read_bytes()) for n in TOP}
    for study in STUDIES:
        base=ROOT/study
        inventory=json.loads((base/"manifest.json").read_bytes())
        entries=inventory.get("files",inventory)
        for name in ["manifest.json",*sorted(entries)]:
            p=(base/name).resolve()
            assert p.is_relative_to(base.resolve()) and p.is_file() and p.suffix in ALLOWED
            assert p.stat().st_size<48*1024**2
            files[study+"/"+name]=digest(p.read_bytes())
    return dict(sorted(files.items()))
def check(z):
    manifest=json.loads(z.read("MANIFEST_SHA256.json"))
    assert len(z.namelist())==len(set(z.namelist()))==len(manifest)+1
    assert set(z.namelist())==set(manifest)|{"MANIFEST_SHA256.json"}
    for n,h in manifest.items():
        assert all(part not in ("",".","..") for part in n.split("/")) and ":" not in n and "\\" not in n
        assert digest(z.read(n))==h,n
    return manifest

def build(output):
    output=output.resolve()
    assert not output.exists() and not output.is_relative_to(ROOT)
    rec=snapshot()
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage=Path(tmp)/"staged.zip"
        with zipfile.ZipFile(stage,"w") as z:
            for n in [*rec,"MANIFEST_SHA256.json"]:
                b=(ROOT/n).read_bytes() if n in rec else (json.dumps(rec,sort_keys=True,separators=(",",":"))+"\n").encode()
                info=zipfile.ZipInfo(n,(1980,1,1,0,0,0));info.external_attr=0o100644<<16
                z.writestr(info,b,compress_type=zipfile.ZIP_STORED if n.endswith((".gz",".png")) else zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(stage) as z:assert check(z)==rec
        assert snapshot()==rec
        os.link(stage,output)
    print(len(rec),digest(output.read_bytes()),output)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("zip",type=Path);p.add_argument("--verify",action="store_true");args=p.parse_args()
    if args.verify:
        with zipfile.ZipFile(args.zip) as z:print(len(check(z)),digest(args.zip.read_bytes()))
    else:build(args.zip)
