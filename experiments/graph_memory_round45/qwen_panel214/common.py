"""Definitions shared with the frozen R39 Qwen pilot."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent
WORK=OUT.parents[1]
R39SRC=WORK/"graph_memory_round39/author_baseline"
sys.path.insert(0,str(R39SRC))
from panel import read,sha,R34,PUB
from reference import CACHE,NAME,DIGEST,EXE,process_state
import gzip,hashlib,json,os,socket,subprocess,time
import numpy as np
import requests


def save(name,value):
    raw=(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode()
    destination=OUT/name
    temporary=destination.with_suffix(destination.suffix+".tmp")
    temporary.write_bytes(gzip.compress(raw,mtime=0) if str(name).endswith(".gz") else raw)
    temporary.replace(destination)


def make_panel():
    rows=read(R34/"features.json.gz")
    pilot=read(R39SRC/"panel.json")["states"]
    ids={q for q,row in rows.items() if row["split"]=="test"}
    assert len(ids)==214 and pilot.keys()<=ids and len(pilot)==10
    first=sorted(pilot,key=lambda q:pilot[q]["position"])
    rest=sorted(ids-pilot.keys(),key=lambda q:hashlib.sha256(("r40-remaining/"+q).encode()).digest())
    assert len(rest)==204
    obj=dict(order=first+rest,pilot=first,remaining=rest,repo={q:rows[q]["repo"] for q in ids},
             candidates={q:len(rows[q]["ids"]) for q in ids},protocol=sha(OUT/"PROTOCOL_RU.md"),
             frozen_214=sha(R34/"features.json.gz"),pilot_panel=sha(R39SRC/"panel.json"))
    save("panel.json",obj)
    print("States",len(ids),"new",len(rest),"candidate entries",sum(obj["candidates"].values()))


if __name__=="__main__":
    make_panel()
