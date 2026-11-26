"""Choose ten independent repositories by state ID hash, before scoring the new reference."""
from pathlib import Path
import gzip
import json
import hashlib
import sys

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
PUB = WORK/"memory_session5/serbench/upstream/data/cal500"
R34 = WORK/"graph_memory_round34/external_transfer/strong"
R39 = ROOT.parent/"set_reader"


def read(path):
    b = path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix == ".gz" else b)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def write(name, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+"\n").encode()
    (ROOT/name).write_bytes(data)


def main():
    data = read(R34/"features.json.gz")
    keys = sorted((q for q,r in data.items() if r["split"]=="test"),
                  key=lambda q:hashlib.sha256(("r39-qwen-panel-v1/"+q).encode()).digest())
    panel = {}
    repos = set()
    for q in keys:
        row = data[q]
        if row["repo"] in repos:
            continue
        panel[q] = {"position":len(panel),"repo":row["repo"],"candidates":len(row["ids"])}
        repos.add(row["repo"])
        if len(panel) == 10:
            break
    write("panel.json",{"states":panel,"protocol":sha(ROOT/"PROTOCOL_RU.md"),"features":sha(R34/"features.json.gz")})
    print("Frozen",len(repos),"repositories",sum(r["candidates"] for r in panel.values()),"candidate entries")


if __name__ == "__main__":
    main()
