"""Check the published research snapshot against physical artifacts and independent score counts."""
import argparse
from hashlib import sha256
import gzip
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
INVENTORY=HERE/"artifact-digests.json"

def load(name):
    raw=(HERE/name).read_bytes()
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)

def sha(data):
    return sha256(data).hexdigest()

def inventory():
    files=sorted(p for p in HERE.rglob("*") if p.is_file() and p!=INVENTORY and "__pycache__" not in p.parts)
    return {p.relative_to(HERE).as_posix():sha(p.read_bytes()) for p in files}

def scientific():
    bench=load("benchmark_history/expanded-graded.json.gz")
    assert len(bench)==54
    gains=[r["scores"]["corroborated"][0]-r["scores"]["lexical"][0] for r in bench.values()]
    assert sum(x>0 for x in gains)==2 and all(x>=0 for x in gains)
    assert abs(sum(gains)/54-5/324)<1e-14
    original=load("benchmark_history/original-results.json")
    assert original["primary"]["win"]==1 and original["primary"]["loss"]==2
    assert original["primary"]["delta"]<0
    controls=load("benchmark_history/community-results.json")
    assert len(controls["original58"])==8
    assert controls["within_method"]["codenib_dense"]["delta"]==0
    checks=load("partner_clock/independent-audit.json")["panels"]
    assert sum(x["counts"]["queries"] for x in checks.values())==2146
    assert sum(x["counts"]["raw_scores"] for x in checks.values())==293231
    vm=load("cochange/physical/vm-steps.json")["total"]
    for k,expected in (("partial8",(308,848,14482)),("classic9",(214,888,12253))):
        assert tuple(vm[k]["warm"][f] for f in ("executions","returned_rows","vm_steps"))==expected
    checked=load("submission/verification.json")
    assert checked["pages"]==4 and checked["files"]==126
    assert checked["sha256"]==sha((HERE/"submission/candidate.zip").read_bytes())
    assert checked["paper_sha256"]==sha((HERE/"submission/paper.pdf").read_bytes())
    assert checked["video_sha256"]==sha((HERE/"demo_video/walkthrough.mp4").read_bytes())
    with ZipFile(HERE/"submission/candidate.zip") as z:
        namelist=z.namelist()
        assert len(set(namelist))==len(namelist)
        files=json.loads(z.read("CONTENT_SHA256.json"))
        assert set(files)==set(namelist)-{"CONTENT_SHA256.json"}
        assert all(sha(z.read(n))==digest for n,digest in files.items())
        assert z.read("coedit-replay.html")==(HERE/"benchmark_history/replay.html").read_bytes()
        assert z.read("paper.pdf")==(HERE/"submission/paper.pdf").read_bytes()
        assert z.read("walkthrough.mp4")==(HERE/"demo_video/walkthrough.mp4").read_bytes()
        assert any(z.read(n)==(HERE/"demo_video/captions.srt").read_bytes() for n in namelist if n.endswith(".srt"))
    # Verify local links in the current entry points and study narratives.
    docs=[ROOT/"README.md",ROOT/"docs/series.md",ROOT/"docs/progress-report.md",HERE/"REPORT_RU.md",
          HERE/"benchmark_history/REPORT_RU.md",HERE/"partner_clock/REPORT_RU.md"]
    for path in docs:
        for target in re.findall(r"\]\(([^)]+)\)",path.read_text(encoding="utf8")):
            if "://" in target or target.startswith("#"):continue
            assert (path.parent/target.split("#")[0]).exists(),(path,target)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--write",action="store_true")
    p.add_argument("--git-index",action="store_true")
    options=p.parse_args()
    scientific()
    found=inventory()
    if options.write:
        INVENTORY.write_text(json.dumps(found,sort_keys=True,indent=2)+"\n",encoding="utf8",newline="\n")
    assert json.loads(INVENTORY.read_bytes())==found
    if options.git_index:
        prefix=HERE.relative_to(ROOT).as_posix()+"/"
        paths={p:ROOT/(prefix+p) for p in [*found,INVENTORY.name]}
        # Git blob IDs are checked in a batch, without disclosing file contents.
        listing=subprocess.check_output(["git","ls-files","--stage","-z","--",prefix],cwd=ROOT).split(b"\0")
        staged={}
        for entry in filter(None,listing):
            info,name=entry.split(b"\t",1)
            _,oid,stage=info.split()
            assert stage==b"0"
            staged[name.decode()[len(prefix):]]=oid.decode()
        assert set(staged)==set(paths)
        computed=subprocess.check_output(["git","hash-object","--stdin-paths"],cwd=ROOT,
                                          input="".join(prefix+path+"\n" for path in paths).encode())
        assert list(staged[p] for p in paths)==computed.decode().splitlines()
    print("Verified",len(found),"research files and their study, interface and archive checks.")
if __name__=="__main__":
    main()
