"""Acquire only identity, timing, and old revision columns from original SWE-rebench-V2 parquet."""
import json, os, time
from pathlib import Path
import fsspec,pyarrow.parquet as pq
D=Path(__file__).resolve().parent
REV="d7608f017a29ab256400ad4b73d5248d97204966"
URL=f"https://huggingface.co/datasets/nebius/SWE-rebench-V2/resolve/{REV}/data/train-00000-of-00001.parquet"
if __name__=="__main__":
    fs=fsspec.filesystem("http",headers={"Accept-Encoding":"identity"})
    with fs.open(URL,"rb",block_size=256*1024) as f:
        parquet=pq.ParquetFile(f)
        print(parquet.schema_arrow.field("meta"),flush=True)
        table=parquet.read(columns=["instance_id","base_commit","created_at","repo"])
    rows={v["instance_id"]:v for v in table.to_pylist()};print(len(rows))
    (D/"task_meta_all.json").write_text(json.dumps(rows,separators=(",",":")),encoding="utf8")
