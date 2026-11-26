"""Read the authors' pinned single-member ZIP and enumerate its title directory."""
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from hashlib import sha256
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import struct
import time
import unicodedata
from urllib.request import Request,urlopen
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent
WORK=Path(os.environ.get("R52_WIKI_WORK","D:/CodexResearch/x20-r52-wiki-directory"))
R50=ROOT.parents[1]/"graph_memory_round50/hyperlink_control"
SOURCE=json.loads((R50/"source.json").read_bytes())
ZIP=WORK/"para_with_hyperlink.zip"
HEADER=re.compile(rb'^\s*\{\s*"id"\s*:\s*"?([0-9]+)"?\s*,\s*"title"\s*:\s*("(?:[^"\\]|\\.)*")\s*,')
def save(path,obj):
    data=(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
    path.write_bytes(gzip.compress(data,mtime=0) if path.suffix==".gz" else data)
def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())
def hashfile(path):
    with path.open("rb") as f:
        return __import__("hashlib").file_digest(f,"sha256").hexdigest()
def fetch(bounds):
    a,b=bounds
    for retry in range(5):
        try:
            req=Request(SOURCE["url"],headers={"Range":f"bytes={a}-{b}","Accept-Encoding":"identity","User-Agent":"memory-research/1"})
            with urlopen(req,timeout=50) as f:
                assert f.status==206 and f.headers.get("Content-Range")==f"bytes {a}-{b}/{SOURCE['compressed_archive']}"
                data=f.read(b-a+2); assert len(data)==b-a+1
                return data
        except Exception:
            if retry==4:raise
            time.sleep(retry+1)
def download():
    WORK.mkdir(exist_ok=True,parents=True)
    if ZIP.exists():
        assert hashfile(ZIP)==SOURCE["zip_sha256"]
        return
    size=SOURCE["compressed_archive"];chunk=8<<20
    ranges=[(a,min(a+chunk,size)-1) for a in range(0,size,chunk)]
    tmp=ZIP.with_suffix(".part");done=tmp.stat().st_size if tmp.exists() else 0
    assert done==size or done%chunk==0
    todo=iter(ranges[(done+chunk-1)//chunk:])
    with ThreadPoolExecutor(5) as pool,tmp.open("ab") as out:
        active=deque(pool.submit(fetch,bounds) for _,bounds in zip(range(5),todo))
        for bounds in todo:
            out.write(active.popleft().result());active.append(pool.submit(fetch,bounds))
        for task in active:out.write(task.result())
    if tmp.stat().st_size!=size or hashfile(tmp)!=SOURCE["zip_sha256"]:raise ValueError("Archive hash mismatch")
    tmp.replace(ZIP)
def title_rows():
    with ZipFile(ZIP) as z,z.open(SOURCE["member"]) as src:
        for line in src:
            h=HEADER.match(line)
            if h is None: raise ValueError("Unexpected source header")
            yield int(h[1]),json.loads(h[2]),line
def panel():
    import pyarrow.parquet as pq
    src=Path("D:/CodexResearch/x20-r32-2wiki/dev.parquet")
    f=pq.ParquetFile(src)
    rows=[(r["_id"],r["question"]) for b in f.iter_batches(columns=["_id","question"]) for r in b.to_pylist()]
    assert len(rows)==len({r[0] for r in rows})==12576
    save(WORK/"questions.json.gz",dict(rows))
    return hashfile(src)
def metadata():
    assert hashfile(ZIP)==SOURCE["zip_sha256"]
    with (WORK/"titles.txt").open("w",encoding="utf8",newline="\n") as out:
        count=0
        for key,title,_ in title_rows():
            assert "\t" not in title and "\n" not in title and "\r" not in title
            out.write(str(key)+"\t"+title+"\n");count+=1
    assert count==SOURCE["records"]
    src=panel()
    save(ROOT/"source.json",dict(documents=count,archive=hashfile(ZIP),url=SOURCE["url"],
         member=SOURCE["member"],dev=src,titles=hashfile(WORK/"titles.txt"),
         questions=hashfile(WORK/"questions.json.gz"),protocol=hashfile(ROOT/"PROTOCOL_RU.md")))
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("stage",choices=["fetch","metadata","all"])
    a=p.parse_args()
    if a.stage in ("fetch","all"):download()
    if a.stage in ("metadata","all"):metadata()

