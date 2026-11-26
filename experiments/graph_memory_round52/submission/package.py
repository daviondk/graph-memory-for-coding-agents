"""Rebuild the standalone demonstration on top of the audited predecessor package."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

D=Path(__file__).resolve().parent
PREVIOUS=D.parents[1]/"graph_memory_round51/submission/candidate.zip"
PIN="fe479dd698377141f26360baccc12afac0ebc5cbdcdfd2aac0c1c4e74daade66"
DOCS=("paper.tex","paper.pdf","sources.bib","README.md","DATA_SOURCES.md","demo.py","start.html",
      "walkthrough.mp4","browser-video.json","verify_candidate.py")
HISTORY=("serve.py","engine.py","cases.json","README.md","test_console.py")

DIRECTORY=("serve.py","index.html","directory.sqlite","audit.json","build.json","test_console.py","README.md")

COMPACT=("extension.py","address_store.py","test_extension.py")

def digest(data):return sha256(data).hexdigest()
def inventory(data):
    return (json.dumps({k:digest(v) for k,v in data.items()},sort_keys=True,indent=2)+"\n").encode()

def compile_paper(files):
    with TemporaryDirectory(dir=D) as tmp:
        tmp=Path(tmp)
        for image in ("core.png","edit.png"):(tmp/image).write_bytes(files[image])
        for name in ("sources.bib","paper.tex"):shutil.copy(D/name,tmp/name)
        subprocess.run(["tectonic","paper.tex"],cwd=tmp,check=True)
        shutil.copy(tmp/"paper.pdf",D/"paper.pdf")

def main():
    p=argparse.ArgumentParser();p.add_argument("--build-paper",action="store_true")
    p.add_argument("--paper-only",action="store_true");a=p.parse_args()
    assert digest(PREVIOUS.read_bytes())==PIN
    with ZipFile(PREVIOUS) as z:files={k:z.read(k) for k in z.namelist()}
    expected=json.loads(files.pop("CONTENT_SHA256.json"))
    assert expected=={k:digest(v) for k,v in files.items()}
    if a.build_paper or a.paper_only:compile_paper(files)
    if a.paper_only:return
    for k in DOCS:files[k]=(D/k).read_bytes()
    for k in HISTORY:files["apps/history/"+k]=(D.parent/"maintenance"/"demo"/k).read_bytes()
    for k in COMPACT:files["apps/history/"+k]=(D.parent/"address_history"/k).read_bytes()
    for k in DIRECTORY:files["apps/directory/"+k]=(D.parent/"directory_demo"/k).read_bytes()
    files["app-inputs.json"]=inventory({k:v for k,v in files.items() if k.startswith("apps/")})
    files["CONTENT_SHA256.json"]=inventory(files)
    with ZipFile(D/"candidate.zip","w") as z:
        for k,v in sorted(files.items()):
            info=ZipInfo(k,(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,v)
    print(len(files),"files",digest((D/"candidate.zip").read_bytes()))
if __name__=="__main__":main()

