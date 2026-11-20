"""Recreate the frozen input layout without reading target solutions."""
import argparse
import json
from pathlib import Path
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from replay import HERE, PIN, bytes_verified, population

HOST="https://huggingface.co"
DATASET="Tongyi-ConvAI/VibeMemBench"


def get(url):
    for attempt in range(5):
        try:
            with urlopen(Request(url,headers={"User-Agent":"within-task-reproduction/1"}),timeout=180) as f:
                return f.read()
        except OSError:
            if attempt==4:
                raise
            time.sleep(2**attempt)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--base",type=Path,required=True)
    args=parser.parse_args()
    base=args.base
    manifest=base/"memory-stage-fetch/source-manifest.json"
    manifest.parent.mkdir(parents=True,exist_ok=True)
    if not manifest.exists():
        manifest.write_bytes(get(f"{HOST}/api/datasets/{DATASET}/revision/{PIN}?blobs=true"))
    # replay.population consumes only three roster fields. Create minimal roster-only
    # files in a fresh cache; do not modify any existing full upstream run record.
    out=base/"memory-stage-audit/raw_bm25"
    out.mkdir(parents=True,exist_ok=True)
    for r in json.loads((HERE/"roster.json").read_bytes()):
        p=out/(r["instance_id"]+".json")
        if not p.exists():
            p.write_text(json.dumps(r),encoding="utf8")
    root,specs=population(base)
    for i,s in enumerate(specs,1):
        p=root/s["rfilename"]
        if not p.exists():
            method="resolve" if s.get("lfs") else "raw"
            url=f"{HOST}/datasets/{DATASET}/{method}/{PIN}/"+quote(s["rfilename"],safe="/")
            p.parent.mkdir(parents=True,exist_ok=True)
            tmp=p.with_suffix(".download")
            tmp.write_bytes(get(url))
            bytes_verified(tmp,s)
            tmp.replace(p)
        bytes_verified(p,s)
        if i%200==0:
            print(f"Verified {i}/{len(specs)} files",flush=True)


if __name__=="__main__":
    main()
