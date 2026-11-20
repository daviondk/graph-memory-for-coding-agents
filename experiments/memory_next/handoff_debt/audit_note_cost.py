"""Inspect public handoff schema without saving any prompts, source prose or generated text."""
import collections
import concurrent.futures
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from download import ROOT,BASE,PIN

def paths(obj):
    if isinstance(obj,dict):
        for k,v in obj.items():
            yield k
            for sub in paths(v):yield k+"."+sub
    if isinstance(obj,list):
        for entry in obj:
            yield from paths(entry)

def main():
    catalog="https://huggingface.co/api/datasets/kc-academy/handoff-debt/tree/"+PIN+"/data/handoffs"
    rr=requests.get(catalog,timeout=30);rr.raise_for_status()
    files=sorted(f["path"] for f in rr.json() if f["path"].endswith(".parquet"))
    def inspect(key):
        response=requests.get(BASE+key+"?download=true",timeout=50);response.raise_for_status()
        reader=pq.ParquetFile(pa.BufferReader(response.content))
        fields=collections.defaultdict(set); counts=collections.Counter()
        for r in reader.read(columns=["handoff_view","handoff_json"]).to_pylist():
            counts[r["handoff_view"]]+=1
            if r["handoff_json"]:fields[r["handoff_view"]].update(paths(json.loads(r["handoff_json"])))
        return {"key":key,"sha256":hashlib.sha256(response.content).hexdigest(),"bytes":len(response.content),
                "schema":reader.schema_arrow.names,"counts":dict(counts),"keys":{k:sorted(v) for k,v in fields.items()}}
    with concurrent.futures.ThreadPoolExecutor(4) as pool:rs=list(pool.map(inspect,files))
    allpaths={f for r in rs for ls in r["keys"].values() for f in ls}
    data={"pinned_files":len(files),"rows":sum(sum(r["counts"].values()) for r in rs),
          "all_payload_keys":sorted(allpaths),"explicit_usage_fields":[k for k in sorted(allpaths) if any(x in k.lower() for x in ["token","usage","cost"])],
          "receipts":rs}
    (ROOT/"note_generation_fields.json").write_text(json.dumps(data,ensure_ascii=False,indent=1),encoding="utf-8")
    print(len(files),data["rows"],data["all_payload_keys"],data["explicit_usage_fields"])
if __name__=="__main__":main()

