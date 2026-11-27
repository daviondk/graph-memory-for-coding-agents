"""Build a deterministic review archive and verify the isolated Python/SQLite entry point."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
FILES = {
    "start.html": HERE/"start.html",
    "paper.pdf":ROUND/"manuscript/paper.pdf",
    "walkthrough.mp4":ROUND/"walkthrough/walkthrough.mp4",
    "captions.srt":ROUND/"walkthrough/captions.srt",
    "one-file.html":ROUND.parent/"graph_memory_round56/manuscript/replay.html",
    **{"two-files/"+n: ROUND/"seed_pair"/n for n in ("demo.py","demo_store.py","demo.html","replay.sqlite","view.html")},
}


def pack(path):
    with ZipFile(path,"w") as archive:
        for name, source in sorted(FILES.items()):
            info=ZipInfo(name,(1980,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED
            info.external_attr=0o644<<16
            archive.writestr(info,source.read_bytes(),compresslevel=6)


def verify(path, root):
    with ZipFile(path) as archive:
        assert set(archive.namelist()) == set(FILES)
        for name,source in FILES.items():
            assert archive.read(name) == source.read_bytes()
        archive.extractall(root)
    work=root/"two-files"
    env={**os.environ,"PYTHONPATH":"","PYTHONNOUSERSITE":"1"}
    args=[sys.executable,"-S","-B","demo.py"]
    subprocess.run([*args,"check-snapshot"],cwd=work,env=env,check=True,stdout=subprocess.DEVNULL)
    server=subprocess.Popen([*args,"open-snapshot","--port","0"],cwd=work,env=env,stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,text=True)
    try:
        line=server.stdout.readline()
        address=re.search(r"http://127\.0\.0\.1:\d+",line)
        assert address, line
        url=address.group(0)
        for case,expected in [("gain",[0,2,3]),("loss",[1,0,0])]:
            with urlopen(url+"/case/"+case,timeout=5) as response:
                receipt=json.load(response)
            assert [len(set(receipt["ranks"][m]) & set(receipt["gold"])) for m in ("sum","joint","placebo")] == expected
        with urlopen(url+"/world/7/4/13",timeout=5) as response:
            value=json.load(response)
        assert value["third"]==8 and value["projection"]==[2]*16
    finally:
        server.terminate()
        server.wait(timeout=10)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    path=HERE/"candidate.zip"
    with TemporaryDirectory(dir=HERE) as folder:
        scratch=Path(folder)
        built=scratch/"rebuilt.zip"
        pack(built)
        if args.verify:
            assert built.read_bytes()==path.read_bytes()
        else:
            path.write_bytes(built.read_bytes())
        verify(path,scratch/"isolated")
    record=dict(entries=len(FILES),bytes=path.stat().st_size,sha256=sha256(path.read_bytes()).hexdigest(),
                extracted_sqlite_routes=["case/gain","case/loss","world/7/4/13"],site_packages=False)
    saved=HERE/"verification.json"
    if args.verify:
        assert record==json.loads(saved.read_bytes())
    else:
        saved.write_text(json.dumps(record,indent=2)+"\n",encoding="utf8")
    print(record)


if __name__=="__main__":
    main()
