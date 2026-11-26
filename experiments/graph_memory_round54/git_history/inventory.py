"""Select and pin Git objects from local read-only mirrors without loading outcomes."""
from pathlib import Path
from hashlib import sha256
import json
import subprocess

HERE=Path(__file__).resolve().parent
BASE=Path("D:/CodexResearch/x20-bench-workspace/work")
MIRRORS={name:BASE / ("memory_session6/validity/mirrors" if name=="pallets/click" else "graph_memory_round1/proofs/transfer/content_mirrors") / name.replace("/","__") for name in ("pallets/click","urllib3/urllib3","tox-dev/tox","psf/requests","pypa/packaging","pytest-dev/pluggy")}

def git(repo,*args):
    return subprocess.check_output(["git","-C",str(repo),*args])
def sha(path):
    return sha256(path.read_bytes()).hexdigest()
def main():
    records={}
    for name,repo in MIRRORS.items():
        revs=git(repo,"rev-list","--first-parent","-n","120","HEAD").decode().splitlines()[::-1]
        assert len(revs)==120
        records[name]=dict(commits=revs,url="https://github.com/"+name)
    pinned=["PROTOCOL_RU.md","inventory.py","../reserve/reserve_store.py","../cutoff/cutoff_store.py","../multi_read/core.py","../../graph_memory_round53/churn/engine.py"]
    out=dict(projects=records,files={p:sha(HERE/p) for p in pinned})
    receipt=HERE/"registration.json"
    if receipt.exists():
        assert json.loads(receipt.read_bytes())==out
    else:
        receipt.write_text(json.dumps(out,indent=2)+"\n",encoding="utf8",newline="\n")
    print(list(records),sha(receipt))
if __name__=="__main__":main()
