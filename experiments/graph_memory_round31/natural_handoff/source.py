"""Pin published files and select benign real takeover pairs without outcomes."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from hashlib import sha256
from urllib.request import urlopen,Request
import json,gzip,shutil,time,sys
import pyarrow.parquet as pq
D=Path(__file__).resolve().parent;P=Path("D:/CodexResearch/x20-r31-handoff")
OLD=Path("D:/CodexResearch/x20-handoff-debt")
SWE=Path("D:/CodexResearch/x20-r27-code-data")
R27=D.parents[1]/"graph_memory_round27/code_boundary";sys.path.insert(0,str(R27))
from prepare import RISK,ALLOW,prod
REV="79244eedc9d58349da0fcf1a2e05916e0ac5af00";REPO="kc-academy/handoff-debt";BASE=f"https://huggingface.co/datasets/{REPO}/resolve/{REV}/";API=f"https://huggingface.co/api/datasets/{REPO}/tree/{REV}/"
def h(x):return sha256(x.encode()).hexdigest()
def sha(p):return sha256(p.read_bytes()).hexdigest()
def save(p,x):
    data=(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(data,mtime=0) if p.suffix==".gz" else data);return sha(p)
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def cohort():
    verified={r["instance_id"]:r for r in pq.read_table(SWE/"verified.parquet",columns=["instance_id","repo","problem_statement","base_commit"]).to_pylist()}
    runs={};cols=["run_id","instance_id","subset","role","predecessor","successor","initial_run_id","checkpoint_id","checkpoint_kind","handoff_view","attempt"]
    for f in sorted(OLD.glob("data-*.parquet")):
        for x in pq.read_table(f,columns=cols).to_pylist():
            if x["instance_id"] in verified and verified[x["instance_id"]]["repo"] in ALLOW and not RISK.search(verified[x["instance_id"]]["problem_statement"]):
                runs[x["run_id"]]=x
    return runs,verified
def tree(kind):
    with urlopen(API+"data/"+kind+"?limit=1000",timeout=30) as fi:r=json.load(fi)
    return [dict(file=x["path"],sha=x["lfs"]["oid"],bytes=x["size"]) for x in r if x["type"]=="file"]
def fetch(x):
    dst=P/x["file"];dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():
        assert dst.stat().st_size==x["bytes"] and sha(dst)==x["sha"];return dst
    if shutil.disk_usage(P).free<4*1024**3:raise RuntimeError("free space")
    for attempt in range(4):
        try:
            with urlopen(BASE+x["file"],timeout=65) as f:raw=f.read(x["bytes"]+1)
            assert len(raw)==x["bytes"] and sha256(raw).hexdigest()==x["sha"];dst.write_bytes(raw);return dst
        except OSError:
            if attempt==3:raise
            time.sleep(attempt+1)
def step():
    runs,meta=cohort();kinds={k:tree(k) for k in ("handoffs","events","checkpoints","trajectories")};save(P/"files.json",kinds)
    total={k:dict(n=len(rows),bytes=sum(x["bytes"] for x in rows)) for k,rows in kinds.items()}
    handoff=kinds["handoffs"]+kinds["checkpoints"];samples=[kinds["events"][0],kinds["trajectories"][0]]
    with ThreadPoolExecutor(4) as ex:paths=list(ex.map(fetch,handoff+samples))
    stats=dict(issues=len({r["instance_id"] for r in runs.values()}),runs=len(runs),role=Counter(r["role"] for r in runs.values()),view=Counter(str(r["handoff_view"]) for r in runs.values()),files=total)
    save(D/"source-probe.json",stats);print(stats)
if __name__=="__main__":step()

