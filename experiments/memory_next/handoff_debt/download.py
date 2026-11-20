"""Fetch and pin author runs only. Prints schemas, never row-level outcomes."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import requests
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
CACHE=Path("D:/CodexResearch/x20-handoff-debt")
PIN="79244eedc9d58349da0fcf1a2e05916e0ac5af00"
BASE="https://huggingface.co/datasets/kc-academy/handoff-debt/resolve/"+PIN+"/"
def one(i):
    key=f"data/runs/data-{i:05}.parquet"
    path=CACHE/Path(key).name
    if not path.exists():
        r=requests.get(BASE+key,timeout=90);r.raise_for_status();path.write_bytes(r.content)
    n=pq.ParquetFile(path).metadata.num_rows
    return {"key":key,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size,"rows":n}
if __name__=="__main__":
    CACHE.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        rs=list(pool.map(one,range(4)))
    (ROOT/"source.json").write_text(json.dumps({"pin":PIN,"base":BASE,"files":rs},indent=1),encoding="utf-8")
    first=pq.ParquetFile(CACHE/"data-00000.parquet")
    print(str(first.schema_arrow)[:10000]);print("records",sum(x["rows"] for x in rs))

