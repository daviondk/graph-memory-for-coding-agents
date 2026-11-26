"""Build the current offline release from the pinned previous archive and study projections."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

D=Path(__file__).resolve().parent
PREVIOUS=D.parents[1]/"graph_memory_round54/submission/candidate.zip"
PIN="735c0cddb063a5c407a44fd573738687b5e291e6b04325d77317deb0d9f3e087"
DOCS=("paper.tex","paper.pdf","sources.bib","README.md","DATA_SOURCES.md","start.html","demo.py","verify_candidate.py")
FILM=D.parent/"demo_video"


def digest(value):
    return sha256(value).hexdigest()


def inventory(files):
    return (json.dumps({name:digest(data) for name,data in files.items()},sort_keys=True,indent=2)+"\n").encode()


def predecessor():
    assert digest(PREVIOUS.read_bytes())==PIN
    with ZipFile(PREVIOUS) as z:
        assert len(set(z.namelist()))==len(z.namelist())
        files={name:z.read(name) for name in z.namelist()}
    prior=json.loads(files.pop("CONTENT_SHA256.json"))
    assert prior==json.loads(inventory(files))
    return files


def extension():
    paths={
        "walkthrough.mp4":FILM/"walkthrough.mp4","captions.srt":FILM/"captions.srt","browser-video.json":FILM/"verification.json",
        "coedit-replay.html":D.parent/"benchmark_history/replay.html",
        "apps/cochange/index.html":D/"cochange/index.html","apps/cochange/serve.py":D/"cochange/serve.py",
        "apps/cochange/vm-steps.json":D.parent/"cochange/physical/vm-steps.json",
        "evidence/coedit-candidates/expanded-results.json":D.parent/"benchmark_history/expanded-results.json",
        "evidence/coedit-candidates/original-results.json":D.parent/"benchmark_history/original-results.json",
        "apps/cochange/events.json.gz":D.parent/"cochange/events.json.gz",
        "evidence/cochange/results.json":D.parent/"cochange/results.json",
        "evidence/cochange/verification.json":D.parent/"cochange/verification.json",
        "evidence/cochange/other-repositories.json":D.parent/"cochange/continuation/results.json",
        "evidence/batched-files/results.json":D.parent/"next_action/results.json",
        "evidence/coedit-candidates/results.json":D.parent/"benchmark_history/results.json",
    }
    return {name:path.read_bytes() for name,path in paths.items()}


def compile_paper(files):
    with TemporaryDirectory(dir=D) as loc:
        scratch=Path(loc)
        for name in ("edit.png","session-read.png","withdrawal.png"):
            (scratch/name).write_bytes(files[name])
        for name in ("paper.tex","sources.bib"):
            shutil.copyfile(D/name,scratch/name)
        subprocess.run(["tectonic","paper.tex"],cwd=scratch,check=True)
        shutil.copyfile(scratch/"paper.pdf",D/"paper.pdf")


def main():
    args=argparse.ArgumentParser();args.add_argument("--build-paper",action="store_true");args.add_argument("--paper-only",action="store_true")
    opts=args.parse_args()
    files=predecessor()
    if opts.build_paper or opts.paper_only:
        compile_paper(files)
    if opts.paper_only:
        return
    files.update({name:(D/name).read_bytes() for name in DOCS})
    files.update(extension())
    files["app-inputs.json"]=inventory({name:data for name,data in files.items() if name.startswith("apps/")})
    files["CONTENT_SHA256.json"]=inventory(files)
    with ZipFile(D/"candidate.zip","w") as z:
        for name,data in sorted(files.items()):
            member=ZipInfo(name,(1980,1,1,0,0,0))
            member.compress_type=ZIP_DEFLATED; member.external_attr=0o100644<<16
            z.writestr(member,data)
    print(len(files),"members",digest((D/"candidate.zip").read_bytes()))


if __name__=="__main__":
    main()
