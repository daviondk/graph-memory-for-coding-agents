"""Download one authors' release with pinned HF revision and file digest."""
from pathlib import Path
from urllib.request import urlopen,Request
import hashlib,sys,os
S=Path("D:/CodexResearch/x20-r54-code-links")
REV="5901e1ee3aff048290db72edf9c63bc498b79ea3"
BASE="https://huggingface.co/datasets/eyuansu71/agent_retrieval_bench/resolve/"+REV+"/releases/"
def fetch(sub,file):
    S.mkdir(exist_ok=True)
    url=BASE+sub+"/"+file
    def get(url):return urlopen(Request(url,headers={"User-Agent":"academic-evaluation/1"}),timeout=180)
    with get(url+".sha256") as r:checksum=r.read().decode().split()[0]
    if not (S/file).exists():
        with get(url+"?download=1") as r,(S/(file+".tmp")).open("wb") as out:
            while block:=r.read(1<<20):out.write(block)
        (S/(file+".tmp")).replace(S/file)
    with (S/file).open("rb") as f:actual=hashlib.file_digest(f,"sha256").hexdigest()
    assert checksum==actual
    print(file,(S/file).stat().st_size,actual)
if __name__=="__main__":fetch("v2_edit2ripple","agent_retrieval_bench_v2_edit2ripple.tar.zst")

