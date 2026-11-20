"""Fetch individually validated immutable ranges to D then validate the complete GGUF."""
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
FILENAME="Qwen3.8-27B-UD-Q4_K_M.gguf"
URL="https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/4af51b3542f775b0a8e4b310bfb3f17e01c306c9/"+FILENAME
SIZE=16564259744
SHA="1bce504dfecd84153666928a41d8a66706f0158d3a317bc5196b72819d7dc529"
PIECE=64*1024*1024
PARTS=ROOT/"range_receipts"
FILE=ROOT/FILENAME


def part(i):
    start=i*PIECE
    end=min(SIZE,start+PIECE)-1
    receipt=PARTS/f"{i:04d}.json"
    if receipt.exists():
        return
    for attempt in range(7):
        try:
            req=Request(URL+f"?download=true&x20part={i}&retry={attempt}",
                headers={"User-Agent":"Qwen-repro-range/1","Range":f"bytes={start}-{end}","Accept-Encoding":"identity"})
            with urlopen(req,timeout=90) as remote, FILE.open("r+b") as out:
                assert remote.status==206 and remote.headers["Content-Range"]==f"bytes {start}-{end}/{SIZE}"
                out.seek(start)
                n=0
                h=hashlib.sha256()
                while block:=remote.read(1024*1024):
                    h.update(block)
                    out.write(block)
                    n+=len(block)
                assert n==end-start+1
            receipt.write_text(json.dumps({"start":start,"end":end,"sha256":h.hexdigest()}))
            return
        except Exception:
            if attempt==6:
                raise
            time.sleep(2**attempt)


if __name__=="__main__":
    PARTS.mkdir(exist_ok=True,parents=True)
    if not FILE.exists():
        with FILE.open("wb") as f:
            f.truncate(SIZE)
    assert FILE.stat().st_size==SIZE
    n=(SIZE+PIECE-1)//PIECE
    with ThreadPoolExecutor(max_workers=12) as pool:
        for count,f in enumerate(as_completed([pool.submit(part,i) for i in range(n)]),1):
            f.result()
            if count%10==0:
                print(count,"of",n,"verified ranges",flush=True)
    with FILE.open("rb") as f:
        digest=hashlib.file_digest(f,"sha256").hexdigest()
    assert digest==SHA,digest
    (ROOT/"model_receipt.json").write_text(json.dumps({"artifact":FILENAME,"source":URL,"sha256":digest,"size":SIZE},indent=2))
    print("whole GGUF verified",digest,flush=True)
