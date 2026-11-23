"""Fetch the one preregistered data shard plus authoring queries and the tokenizer."""
import concurrent.futures
import hashlib
import json
import sys
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
CACHE = Path("D:/CodexResearch/x20-isetrace-runtime/inputs")
RAW = "valiere/ISETrace", "e40e04d41c04e4eb4bae181ebdd41b61c688081b"
QUERY = "HazeLocus/ISETrace-Memory-Queries", "3130aeeaeb2b8d292c29f4c8e23303be7463732c"
E5 = "intfloat/e5-base-v2", "f52bf8ec8c7124536f0efb74aca902b2995e5bcd"
SPECS = [(RAW, "datasets","trajectories/trajectories-00000.jsonl"),
         (QUERY,"datasets","query-authoring/isetrace-v7-raw.jsonl"),
         (QUERY,"datasets","query-authoring/isetrace-v7-raw.jsonl.metadata.jsonl"),
         (E5,"models","tokenizer.json")]

def fetch(spec):
    (name, rev), kind, path = spec
    parent=path.rpartition("/")[0]
    url=f"https://huggingface.co/api/{kind}/{name}/tree/{rev}" + ("/"+parent if parent else "")
    reply=requests.get(url,timeout=50)
    reply.raise_for_status()
    item=next(x for x in reply.json() if x["path"]==path)
    url=f"https://huggingface.co/{'datasets/' if kind=='datasets' else ''}{name}/resolve/{rev}/{path}"
    dest=CACHE/path
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():
        with requests.get(url,stream=True,timeout=(30,90)) as response:
            response.raise_for_status()
            tmp=dest.with_suffix(dest.suffix+".partial")
            with tmp.open("wb") as out:
                for chunk in response.iter_content(4*1024**2):
                    out.write(chunk)
            assert tmp.stat().st_size==item["size"],(path,tmp.stat().st_size,item["size"])
            tmp.replace(dest)
    with dest.open("rb") as f:sha=hashlib.file_digest(f,"sha256").hexdigest()
    assert dest.stat().st_size==item["size"]
    if item.get("lfs"):
        assert sha==item["lfs"]["oid"]
    else:
        raw=dest.read_bytes()
        assert hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()==item["oid"]
    print("ready",path, dest.stat().st_size,flush=True)
    return {"path":path,"url":url,"sha256":sha,"size":item["size"]}

if __name__=="__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:records=list(ex.map(fetch,SPECS))
    (ROOT/"source-lock.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf8")
