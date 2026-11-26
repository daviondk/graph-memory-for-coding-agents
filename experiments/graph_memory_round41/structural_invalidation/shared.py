"""Fixed signed inputs and streaming local access to only selected change events."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys

import pyarrow.parquet as pq

D=Path(__file__).resolve().parent
W=D.parents[1];R40=W/"graph_memory_round40";G=R40/"guarded_updates";N=R40/"natural_invalidations"
V=W/"graph_memory_round38/edit_ready";RAW=Path("D:/CodexResearch/x20-r31-handoff")
REV="5508f8be81025d8aa90726b1e06aef4ea484e577"
SRC=Path("D:/CodexResearch/x20-r40-memtrace-runtime")/REV/"src"
sys.path[:0]=[str(SRC),str(N)]
from memtrace.semantic_memory import SemanticStore
from score import select


def h(s):
    return hashlib.sha256(s.encode("utf8")).hexdigest()


def sha(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def read(path):
    b=path.read_bytes();return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)


def save(name,obj):
    b=(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p=D/name;p.write_bytes(gzip.compress(b,compresslevel=4,mtime=0) if p.suffix==".gz" else b)


def signed(d,name):
    p=d/name;assert sha(p)==read(d/"manifest.json")["files"][name];return read(p)


def inputs():
    assert sha(D/"PROTOCOL_RU.md")=="d739e7c7b0ba8356fc9936b3c0ced4a8bf04366b931cf251fcf5027102680fdd"
    assert sha(RAW/"files.json")==read(V/"input-seal.json")["source_manifest"]
    ev=signed(G,"selections.json.gz");plans=signed(G,"guarded-plans.json.gz");vis=signed(V,"visible.json.gz")
    return ev,plans,vis


def case_id(ev):return h(ev["run"]+"/"+str(ev["receipt"]))


def stream(events):
    wanted=defaultdict(dict)
    for e in events:wanted[e["run"]][e["receipt"]]=e
    memo={};seen=set()
    for shard in read(RAW/"files.json")["events"]:
        file=RAW/shard["file"];assert sha(file)==shard["sha"]
        for batch in pq.ParquetFile(file).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for idx,(run,at) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in memo:memo[run]=h(run)
                rid=memo[run]
                if rid not in wanted or at not in wanted[rid]:continue
                row=wanted[rid][at];key=case_id(row)
                assert key not in seen;seen.add(key)
                # Only these fields of the trusted stored observation are used; contents are never evaluated.
                ob=json.loads(batch.column(2)[idx].as_py())["raw"]["observation"]
                assert ob["command"]=="str_replace" and not ob["is_error"] and h(ob["path"].removeprefix("/testbed/").removeprefix("/workspace/"))==row["path"]
                yield key,row,ob["path"].endswith(".py"),ob["old_content"],ob["new_content"]
    assert len(seen)==len(events)

