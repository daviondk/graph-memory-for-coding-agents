import gzip
import hashlib
import json
from pathlib import Path
import sys
D=Path(__file__).resolve().parent
BASE=D.parent/"baseline"
sys.path.insert(0,str(BASE))
from study import raw,digest,ci_records
R50=BASE.parents[1]/"graph_memory_round50"
DATA={"2wiki":(R50/"gate_confirmation",Path("D:/CodexResearch/x20-r50-gate-confirmation")),
      "hotpot":(D.parent/"routing",Path("D:/CodexResearch/x20-r51-hotpot-routing"))}


def put(n,x):
    b=(json.dumps(x,sort_keys=True,allow_nan=False,indent=None if n.endswith(".gz") else 2)+"\n").encode()
    (D/n).write_bytes(gzip.compress(b,compresslevel=9,mtime=0) if n.endswith(".gz") else b)


def source(p):
    if p=="2wiki":
        choices=raw(BASE/"decisions.json.gz")["gate_confirmation"]
        ctx=raw(BASE/"matched-contexts.json.gz")["gate_confirmation"]
        newp=raw(BASE/"new-prompts.json.gz");newa=raw(BASE/"new-answers.json.gz")
    else:
        b=BASE/"confirm"
        choices=raw(b/"choices.json.gz");ctx=raw(b/"contexts.json.gz")
        newp=raw(b/"new-prompts.json.gz");newa=raw(b/"new-answers.json.gz")
    return choices,ctx,newp,newa
