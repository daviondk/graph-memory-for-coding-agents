"""Charge first construction to the first query on each pair. No prepared plane file is read."""
from collections import defaultdict
from contextlib import closing
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import sqlite3
import sys
from time import perf_counter_ns

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"joint_packets"))
from bank import DB, SCALE, LIMIT, Snapshot, library, build, choose

def run():
    rng=random.Random(47071)
    upstream=HERE.parent/"joint_packets/pairs.json.gz"
    panel=[r for r in json.loads(gzip.decompress(upstream.read_bytes())) if "uniform" in r["parts"]]
    lib=library()
    snapshots={}
    sources={}
    with closing(sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True)) as db:
        for q, in db.execute("SELECT q FROM query ORDER BY q"):
            rows=db.execute("SELECT id,tokens,utility FROM node WHERE q=? ORDER BY rank",(q,))
            snapshots[q]=Snapshot([(i,c,round(u*SCALE)) for i,c,u in rows])
            sources[q]=defaultdict(set)
            for i,s in db.execute("SELECT DISTINCT id,source FROM span WHERE q=?",(q,)):
                sources[q][s].add(i)
    output=[]
    for rep in range(5):
        rng.shuffle(panel)
        for case in panel:
            q=case["q"]; snap=snapshots[q]
            left=sources[q][case["s"]];right=sources[q][case["t"]]
            marks=tuple(int(i in left)+2*int(i in right) for i in snap.ids)
            direct=snap.native(lib,marks)
            points=[(rng.randint(-LIMIT,LIMIT),rng.randint(-LIMIT,LIMIT)) for _ in range(16)]
            durations={};answers={};construct=None
            methods=["materialize","native"];rng.shuffle(methods)
            for method in methods:
                reads=[];packets=[]
                if method=="materialize":
                    start=perf_counter_ns()
                    planes,_=build(lib,snap,marks)
                    construct=perf_counter_ns()-start
                for x,y in points:
                    start=perf_counter_ns()
                    item=direct(x,y) if method=="native" else choose(planes,x,y)
                    elapsed=perf_counter_ns()-start
                    reads.append(elapsed);packets.append(item)
                durations[method]=reads;answers[method]=packets
            assert answers["native"]==answers["materialize"]
            if rep:
                output.append([q,case["pair"],rep,construct,durations["materialize"],durations["native"]])
    raw=json.dumps(output,separators=(",",":")).encode()
    (HERE/"timings.json.gz").write_bytes(gzip.compress(raw,mtime=0))
    metadata=dict(protocol=hashlib.sha256((HERE/"PROTOCOL_RU.md").read_bytes()).hexdigest(),
                  inputs=hashlib.sha256(upstream.read_bytes()).hexdigest(),reader=hashlib.sha256(DB.read_bytes()).hexdigest(),
                  seed=47071,pairs=len(panel),repeats=4,equalities=len(panel)*5*16,native_source=hashlib.sha256((HERE.parent/"joint_packets/kernels.cpp").read_bytes()).hexdigest())
    (HERE/"run.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf8")
    print(metadata)
if __name__=="__main__":
    run()
