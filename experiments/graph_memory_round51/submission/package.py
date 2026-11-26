"""Rebuild the offline ICDE candidate from the verified R50 archive and R51 projections."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]/"graph_memory_round50/submission/candidate.zip"
PRIOR="008f543f24fe05219e385cfd30c0bb557d316b4dbf2821d371fd5befa9622afe"
RUNTIME=("server.py","replay.py","rank_view.py","rank.html","index.html","rank.sqlite","replay.sqlite")
OVERRIDE=("paper.pdf","paper.tex","sources.bib","demo.py","start.html","README.md","walkthrough.mp4","verify_candidate.py","browser-video.json","DATA_SOURCES.md","LICENSE-2Wiki.txt")

def h(data):
    return sha256(data).hexdigest()

def inventory(files):
    return (json.dumps({n:h(v) for n,v in files.items()},indent=2,sort_keys=True)+"\n").encode()

def build(output,compile_pdf=False):
    assert h(BASE.read_bytes())==PRIOR
    with ZipFile(BASE) as z:
        files={name:z.read(name) for name in z.namelist()}
    expected=json.loads(files.pop("CONTENT_SHA256.json"))
    assert expected=={k:h(v) for k,v in files.items()}
    if compile_pdf:
        with TemporaryDirectory(dir=ROOT) as folder:
            tmp=Path(folder)
            for name in ("core.png","edit.png"):
                (tmp/name).write_bytes(files[name])
            for name in ("paper.tex","sources.bib"):
                shutil.copyfile(ROOT/name,tmp/name)
            subprocess.run(["tectonic","--keep-logs","paper.tex"],cwd=tmp,check=True)
            shutil.copyfile(tmp/"paper.pdf",ROOT/"paper.pdf")
    for name in OVERRIDE:
        files[name]=(ROOT/name).read_bytes()
    for name in RUNTIME:
        files["apps/policies/"+name]=(ROOT.parent/"policy_replay"/name).read_bytes()
    files["app-inputs.json"]=inventory({k:v for k,v in files.items() if k.startswith("apps/")})
    files["CONTENT_SHA256.json"]=inventory(files)
    with ZipFile(output,"w") as z:
        for name, data in sorted(files.items()):
            item=ZipInfo(name,(1980,1,1,0,0,0))
            item.compress_type=ZIP_DEFLATED
            item.external_attr=0o100644<<16
            z.writestr(item,data)
    print(f"{len(files)} files, {output.stat().st_size} bytes, SHA256 {h(output.read_bytes())}")

if __name__=="__main__":
    arg=argparse.ArgumentParser(description=__doc__);arg.add_argument("--build-paper",action="store_true")
    arg.add_argument("--output",type=Path,default=ROOT/"candidate.zip")
    opts=arg.parse_args();build(opts.output,opts.build_paper)

