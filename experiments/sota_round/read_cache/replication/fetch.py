"""Fetch only the 300 previously published past-session logs by pinned Git blob."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen,Request
from replay import HERE


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--data",type=Path,required=True)
    root=ap.parse_args().data
    src=json.loads((HERE/"sources.json").read_bytes())
    assert len(src["files"])==300
    for item in src["files"]:
        local=root/item["relative"]
        if local.exists():
            raw=local.read_bytes()
        else:
            path="cases/SWEContextBench Lite Past Experience/"+local.name
            url="https://raw.githubusercontent.com/jiayuanz3/SWEContextBench/"+src["github"]+"/"+quote(path,safe="/")
            with urlopen(Request(url,headers={"User-Agent":"within-session-replay/1"}),timeout=90) as res:
                raw=res.read()
        assert len(raw)==item["size"] and hashlib.sha256(raw).hexdigest()==item["sha256"]
        assert hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()==item["git_blob"]
        if not local.exists():
            local.parent.mkdir(parents=True,exist_ok=True)
            local.write_bytes(raw)


if __name__=="__main__":
    main()
