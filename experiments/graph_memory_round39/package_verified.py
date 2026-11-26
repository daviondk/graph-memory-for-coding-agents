"""Build or independently inspect the deterministic R39 ZIP."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import zipfile
from verify import ROOT, TOP, STUDIES, digest, require, valid_name, verify

MANIFEST = "MANIFEST_SHA256.json"

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":")) + "\n").encode()

def inspect(archive):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) and all(valid_name(x) for x in names), "invalid ZIP inventory")
        require(sum(i.file_size for i in z.infolist()) < 512*1024**2, "unexpected expanded size")
        files = json.loads(z.read(MANIFEST))
        require(set(names) == set(files)|{MANIFEST} and MANIFEST not in files, "archive manifest mismatch")
        release = json.loads(z.read("release.json")); require(tuple(release["completed"]) == STUDIES, "incomplete archive")
        exact = set(TOP)
        for study in STUDIES:
            key = study+"/manifest.json"; exact.add(key)
            require(digest(z.read(key)) == release["manifests"][study], key)
            child = json.loads(z.read(key)); child = child.get("files",child)
            for name, status in child.items():
                require(valid_name(name) and name != "manifest.json", name)
                target = study+"/"+name
                exact.add(target)
                require(files[target] == (status if isinstance(status,str) else status["sha256"]),target)
        require(exact == set(files), "unexpected unsigned ZIP member")
        for name, sha in files.items():
            require(digest(z.read(name)) == sha, name)
        return files

def build(output):
    output = output.resolve()
    require(not output.exists() and not output.is_relative_to(ROOT), "select a new ZIP outside the directory of studies")
    files = verify()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        tmp = Path(directory)/"staged.zip"
        with zipfile.ZipFile(tmp,"x") as z:
            for name in [*files,MANIFEST]:
                data = encoded(files) if name == MANIFEST else (ROOT/name).read_bytes()
                info = zipfile.ZipInfo(name, (1980,1,1,0,0,0)); info.create_system=3; info.external_attr=0o100644<<16
                z.writestr(info,data,compress_type=zipfile.ZIP_STORED if name.endswith((".gz",".npz",".png")) else zipfile.ZIP_DEFLATED)
        require(inspect(tmp) == verify(), "source changed during packaging")
        os.link(tmp,output)
    return files

if __name__ == "__main__":
    cli = argparse.ArgumentParser(); cli.add_argument("zip",type=Path); cli.add_argument("--verify",action="store_true");args=cli.parse_args()
    records = inspect(args.zip) if args.verify else build(args.zip)
    print(len(records),digest(args.zip.read_bytes()),args.zip)
