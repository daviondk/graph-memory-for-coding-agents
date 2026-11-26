from pathlib import Path
from collections import defaultdict
import gzip,hashlib,importlib.util,json,sys

D=Path(__file__).resolve().parent;W=D.parents[1];P=D.parent/"prospective_read"
F=W/"graph_memory_round42/future_reads";G=W/"graph_memory_round40/guarded_updates";H=W/"graph_memory_round37/code_visibility"
V=W/"graph_memory_round40/view_fidelity";RAW=Path("D:/CodexResearch/x20-r31-handoff")
METHODS=("prior","rebase","verbatim","interior","boundary")
BUDGETS=(512,2048,8192)

def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def signed(d,n):
    assert sha(d/n)==read(d/"manifest.json")["files"][n];return read(d/n)
def save(n,obj):
    p=D/n;b=(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,compresslevel=4,mtime=0) if p.suffix==".gz" else b)

def module(n,p):
    spec=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def collect(events):
    import pyarrow.parquet as pq
    needed=defaultdict(set)
    for r in events:needed[r["run"]].update((r["at"],r["view"],r["receipt"]))
    memo={};result=defaultdict(dict)
    for shard in read(RAW/"files.json")["events"]:
        f=RAW/shard["file"];assert sha(f)==shard["sha"]
        for batch in pq.ParquetFile(f).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for j,(run,at) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in memo:memo[run]=h(run)
                r=memo[run]
                if r not in needed or at not in needed[r]:continue
                env=json.loads(batch.column(2)[j].as_py())["raw"]
                if "action" in env:
                    action=env["action"];item={n:action[n] for n in ("command","path","old_str","new_str")}
                else:
                    observation=env["observation"];item={n:observation[n] for n in ("command","path","content","is_error")}
                # Private old/new source snapshots are never forwarded.
                result[r][at]=item
    assert all(set(result[r])==ids for r,ids in needed.items())
    return result

