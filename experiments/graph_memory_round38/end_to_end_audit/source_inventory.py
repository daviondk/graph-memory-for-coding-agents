"""Verify every permitted file against the pinned public tree without uploading inputs."""
from hashlib import sha1,sha256
from urllib.parse import quote
import json
from inputs import D,V,HF,fetch,save
def check(r,file):
    raw=file.read_bytes(); size=len(raw);assert r["size"]==size
    if r.get("lfs"):assert r["lfs"]["oid"]==sha256(raw).hexdigest()
    else:assert r["oid"]==sha1(f"blob {size}\0".encode()+raw).hexdigest()
    return dict(path=r["path"],bytes=size,sha256=sha256(raw).hexdigest(),git_oid=r["oid"],lfs=r.get("lfs",{}).get("oid"))
def main():
    repo=f"https://huggingface.co/api/datasets/Tongyi-ConvAI/VibeMemBench/tree/{HF}"
    base=json.loads(fetch(repo)); tree=json.loads(fetch(repo+"/history/python/ipython__traitlets?recursive=true&expand=false"))
    rows=[v for v in tree if v["type"]=="file"]
    upstream_rows=len(rows)
    present={v["path"] for v in rows if (V/"benchmark"/v["path"]).is_file()}
    excluded=[v["path"] for v in rows if v["path"] not in present]
    rows=[v for v in rows if v["path"] in present];assert len(rows)==12 and upstream_rows==18
    result=[check(a,V/"benchmark"/a["path"]) for a in rows]
    test=check(next(a for a in base if a["path"]=="test.parquet"),V/"benchmark/test.parquet")
    save(D/"public-files.json",{"upstream_count":upstream_rows,"excluded_without_reading":excluded,"tree_url":repo,"test":test,"histories":result,"verified_bytes":sum(r["bytes"] for r in result)})
    print("published history blobs",len(result),"verified bytes",sum(r["bytes"] for r in result))
if __name__=="__main__":main()
