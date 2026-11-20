"""Fetch immutable causal source histories and expose repository-ready events on D."""
import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

PIN = "11164976b4f920cdb0d0cd570ca572e49acea1e8"
HOST = "https://huggingface.co"
DATASET = "Tongyi-ConvAI/VibeMemBench"
BASE = Path(os.environ.get("VIBE_BENCH_HOME", "D:/CodexResearch/x20-official-vibe/VibeMemBench"))
DATA = BASE/"benchmark"
META = BASE/"memory-stage-fetch"
FOCUS = ["brazilian-utils__brutils-python","s-knibbs__dataclasses-jsonschema"]


def get_bytes(url):
    for attempt in range(6):
        try:
            req=Request(url,headers={"User-Agent":"VibeMemBench-ResearchStage/1.0"})
            with urlopen(req,timeout=120) as f:
                return f.read()
        except OSError:
            if attempt==5:
                raise
            time.sleep(1 + 2**attempt)


def allowed_specs():
    import pyarrow.parquet as pq
    META.mkdir(exist_ok=True,parents=True)
    info = META/"source-manifest.json"
    if not info.exists():
        info.write_bytes(get_bytes(f"{HOST}/api/datasets/{DATASET}/revision/{PIN}?blobs=true"))
    manifest=json.loads(info.read_bytes())
    assert manifest["sha"]==PIN
    target=next(x for x in manifest["siblings"] if x["rfilename"]=="test.parquet")
    fetch(target)
    groups=defaultdict(list)
    for row in pq.read_table(DATA/"test.parquet",columns=["repo","instance_id","language"]).to_pylist():
        groups[row["repo"].replace("/","__")].append(int(row["instance_id"].rsplit("-",1)[1]))
    specs=defaultdict(list)
    for item in manifest["siblings"]:
        p=item["rfilename"].split("/")
        if len(p)==5 and p[-1].endswith(".traj.json") and p[2] in groups and int(p[3].rsplit("-",1)[1])<max(groups[p[2]]):
            specs[p[2]].append(item)
    assert len(groups)==len(specs)==90
    return specs


def fetch(item):
    name=item["rfilename"]
    target=DATA/name
    target.parent.mkdir(exist_ok=True,parents=True)
    lfs=item.get("lfs")
    def valid(data):
        if len(data)!=item["size"]:
            return False
        if lfs:
            return hashlib.sha256(data).hexdigest()==lfs["sha256"]
        return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\x00"+data).hexdigest()==item["blobId"]
    if target.exists() and valid(target.read_bytes()):
        return
    flavor="resolve" if lfs else "raw"
    data=get_bytes(f"{HOST}/datasets/{DATASET}/{flavor}/{PIN}/{name}")
    if not valid(data):
        raise ValueError("Invalid downloaded bytes "+name)
    temp=target.with_suffix(".part")
    temp.write_bytes(data)
    temp.replace(target)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--workers",type=int,default=24)
    p.add_argument("--focus-only",action="store_true")
    a=p.parse_args()
    specs=allowed_specs()
    order=FOCUS+[r for r in sorted(specs,key=lambda r:len(specs[r])) if r not in FOCUS]
    if a.focus_only:
        order=FOCUS
    print("causal union", sum(map(len,specs.values())), "histories", flush=True)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        work=[(repo,[pool.submit(fetch,it) for it in specs[repo]]) for repo in order]
        for repo,futures in work:
            for future in futures:
                future.result()
            (META/(repo+".ready.json")).write_text(json.dumps({"repo":repo,"verified_files":len(specs[repo]),
                "verified_bytes":sum(s["size"] for s in specs[repo])}),encoding="utf8")
            print(repo,len(futures),flush=True)
