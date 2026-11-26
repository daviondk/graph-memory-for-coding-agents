"""Build the R53 offline ZIP from the pinned R52 archive, replacing only declared members."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
from zipfile import ZIP_DEFLATED,ZipFile,ZipInfo
D=Path(__file__).resolve().parent
PREVIOUS=D.parents[1]/"graph_memory_round52/submission/candidate.zip"
PIN="c072f258d4407d49962bcb5a5c6725a9c55e2c664f06471055f145cd043a6d27"
DOCS=("paper.tex","paper.pdf","sources.bib","README.md","DATA_SOURCES.md","demo.py","start.html","verify_candidate.py")
CHURN=("source.py","engine.py","demo/server.py","demo/trace.json","demo/index.html","demo/verify_http.py")
def digest(data):return sha256(data).hexdigest()
def inventory(files):return (json.dumps({k:digest(v) for k,v in files.items()},sort_keys=True,indent=2)+"\n").encode()
def predecessor():
    assert digest(PREVIOUS.read_bytes())==PIN
    with ZipFile(PREVIOUS) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        files={k:z.read(k) for k in z.namelist()}
    expected=json.loads(files.pop("CONTENT_SHA256.json"))
    assert expected=={k:digest(v) for k,v in files.items()}
    return files
def compile_paper(files):
    with TemporaryDirectory(dir=D) as temp:
        t=Path(temp)
        for n in ("core.png","edit.png"):(t/n).write_bytes(files[n])
        for n in ("paper.tex","sources.bib"):shutil.copyfile(D/n,t/n)
        subprocess.run(["tectonic","paper.tex"],cwd=t,check=True)
        shutil.copyfile(t/"paper.pdf",D/"paper.pdf")
def main():
    p=argparse.ArgumentParser();p.add_argument("--build-paper",action="store_true");opt=p.parse_args()
    files=predecessor()
    if opt.build_paper:compile_paper(files)
    for n in DOCS:files[n]=(D/n).read_bytes()
    for n in CHURN:files["apps/churn/"+n]=(D.parent/"churn"/n).read_bytes()
    files["app-inputs.json"]=inventory({k:v for k,v in files.items() if k.startswith("apps/")})
    files["CONTENT_SHA256.json"]=inventory(files)
    with ZipFile(D/"candidate.zip","w") as z:
        for n,v in sorted(files.items()):
            i=ZipInfo(n,(1980,1,1,0,0,0));i.compress_type=ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,v)
    print(len(files),"members",digest((D/"candidate.zip").read_bytes()))
if __name__=="__main__":main()
