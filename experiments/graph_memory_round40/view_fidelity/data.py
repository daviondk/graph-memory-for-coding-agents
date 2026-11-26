from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import pyarrow.parquet as pq
D=Path(__file__).resolve().parent
W=D.parents[1]
SPAN=D.parent/"span_updates"
NAT=D.parent/"natural_invalidations"
R38=W/"graph_memory_round38/edit_ready"
RAW=Path("D:/CodexResearch/x20-r31-handoff")


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)


def save(p,v):
    b=(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,compresslevel=4,mtime=0) if p.suffix==".gz" else b)


def split():
    hist=SPAN/"scored.json.gz"
    assert sha(hist)==read(SPAN/"results.json")["forecasts"]=="ee88ec13e8b595bc452ebf9492a51ac30598d8556660274b4b55122142998d92"
    rows=read(hist)
    issues=sorted({r["issue"] for r in rows},key=lambda i:h("r40-view-fidelity|"+i))
    test=set(issues[::3])
    return rows,test


def fixed():
    for p in (NAT/"plans.json.gz",R38/"visible.json.gz",R38/"schedule.json.gz"):
        assert sha(p)==read(p.parent/"manifest.json")["files"][p.name]
    assert sha(RAW/"files.json")==read(R38/"input-seal.json")["source_manifest"]
    return read(NAT/"plans.json.gz"),read(R38/"visible.json.gz"),read(R38/"schedule.json.gz")


def raw_events(rows,receipts=True):
    wanted=defaultdict(set)
    for r in rows:
        wanted[r["rid"]].add(r["view"])
        if receipts:
            wanted[r["rid"]].update((r["event"],r["receipt"]))
    found=defaultdict(dict);lookup={}
    for s in read(RAW/"files.json")["events"]:
        path=RAW/s["file"]
        assert sha(path)==s["sha"]
        for batch in pq.ParquetFile(path).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            ids,ats=batch.column(0).to_pylist(),batch.column(1).to_pylist()
            for j,(run,at) in enumerate(zip(ids,ats)):
                if run not in lookup:
                    lookup[run]=h(run)
                rid=lookup[run]
                if rid in wanted and at in wanted[rid]:
                    assert at not in found[rid]
                    found[rid][at]=json.loads(batch.column(2)[j].as_py())["raw"]
    assert set(found)==set(wanted) and all(set(found[r])==wanted[r] for r in wanted)
    return found
