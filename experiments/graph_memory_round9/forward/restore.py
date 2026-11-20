"""Rehydrate only pinned, previously observed Java files from the recorded public URLs."""
import argparse
import concurrent.futures
from common import *
from acquire import get

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("panel",choices=["primary","holdout"],nargs="?",default="primary")
    args=ap.parse_args()
    folder=Path("holdout") if args.panel=="holdout" else Path(".")
    registry={}
    for c in read(folder/"sources.json.gz").values():
        for f in c["files"].values():
            for s in ("old","new"):
                b=f.get(s+"_blob")
                if b and "error" not in b:registry[b["cache"]]=b
    def restore(b):
        p=CACHE/b["cache"]
        if not p.resolve().is_relative_to((CACHE/"raw").resolve()):raise ValueError(p)
        if p.is_file() and sha(p.read_bytes())==b["sha256"]:return
        data=get(b["url"])
        oid=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
        assert sha(data)==b["sha256"] and oid==b["git_blob"] and len(data)==b["size"]
        p.parent.mkdir(parents=True,exist_ok=True)
        t=p.with_suffix(".part");t.write_bytes(data);t.replace(p)
    with concurrent.futures.ThreadPoolExecutor(6) as workers:list(workers.map(restore,registry.values()))
    print(len(registry),"source files match pinned checksums")
if __name__=="__main__":main()
