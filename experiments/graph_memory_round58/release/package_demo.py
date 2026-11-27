"""Package the current three visitor scenarios and exercise the extracted artifact."""
import argparse
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

HERE=Path(__file__).resolve().parent
ROUND=HERE.parent
EXP=ROUND.parent
TWO=EXP/"graph_memory_round57"/"seed_pair"
FILES={"start.html":HERE/"start.html","restart.html":ROUND/"demo/index.html",
       "paper.pdf":ROUND/"manuscript/paper.pdf","walkthrough.mp4":ROUND/"walkthrough/walkthrough.mp4",
       "captions.srt":ROUND/"walkthrough/captions.srt","one-file.html":EXP/"graph_memory_round56/manuscript/replay.html",
       **{"two-files/"+n:TWO/n for n in ("demo_store.py","demo.py","demo.html","replay.sqlite","view.html")}}


class Links(HTMLParser):
    def handle_starttag(self,tag,attrs):
        if tag=="a":
            self.links.append(dict(attrs)["href"])


def build(path):
    with ZipFile(path,"w") as archive:
        for name,p in sorted(FILES.items()):
            info=ZipInfo(name,(1980,1,1,0,0,0))
            info.external_attr=0o644<<16
            info.compress_type=ZIP_DEFLATED
            archive.writestr(info,p.read_bytes(),compresslevel=6)


def inspect(path,root):
    with ZipFile(path) as archive:
        assert set(archive.namelist())==set(FILES)
        assert all(archive.read(n)==p.read_bytes() for n,p in FILES.items())
        archive.extractall(root)
    links=Links()
    links.links=[]
    links.feed((root/"start.html").read_text(encoding="utf8"))
    assert all((root/name).is_file() for name in links.links)
    assert (root/"paper.pdf").read_bytes().startswith(b"%PDF-")
    folder=root/"two-files"
    cli=[sys.executable,"-I","-B","-S","-c",
         "import sys,runpy;sys.path.insert(0,'.');sys.argv=['demo.py',*sys.argv[1:]];runpy.run_path('demo.py',run_name='__main__')"]
    subprocess.run([*cli,"check-snapshot"],cwd=folder,check=True,capture_output=True)
    process=subprocess.Popen([*cli,"open-snapshot","--port","0"],cwd=folder,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        address=re.search(r"http://127\.0\.0\.1:\d+",process.stdout.readline()).group()
        for case,hits in (("gain",[0,2,3]),("loss",[1,0,0])):
            with urlopen(address+"/case/"+case,timeout=5) as resp:
                data=json.load(resp)
            assert [len(set(data["ranks"][m])&set(data["gold"])) for m in ("sum","joint","placebo")]==hits
        with urlopen(address+"/world/7/4/13",timeout=5) as resp:
            assert json.load(resp)["third"]==8
    finally:
        process.terminate()
        process.wait(timeout=10)
    return {"sha256":sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size,
            "members":sorted(FILES),"local_start_links":links.links,"isolated_sqlite_endpoints":3}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--verify",action="store_true")
    args=p.parse_args()
    current=HERE/"candidate.zip"
    with TemporaryDirectory(dir=HERE) as tmp:
        root=Path(tmp)
        rebuilt=root/"candidate.zip"
        build(rebuilt)
        if args.verify:
            assert rebuilt.read_bytes()==current.read_bytes()
        else:
            current.write_bytes(rebuilt.read_bytes())
        record=inspect(current,root/"extracted")
    receipt=HERE/"verification.json"
    if args.verify:
        assert record==json.loads(receipt.read_bytes())
    else:
        receipt.write_text(json.dumps(record,indent=2)+"\n",encoding="utf8")
    print(record["sha256"],record["bytes"],len(record["members"]))
