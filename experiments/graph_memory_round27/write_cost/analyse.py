"""Summarize full-lifecycle costs per independent observed episode."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median
import numpy as np
import sys

HERE=Path(__file__).resolve().parent
def load(name):
    path=HERE/name
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)
def main():
    prefix="promotion-" if "--promotion" in sys.argv else ""
    rows=load(prefix+"times.json.gz")
    by=defaultdict(list)
    for rep,corpus,key,method,ingest,queries in rows:
        total=ingest
        traffic=0
        for i in range(len(queries)+1):
            if i:
                total+=queries[i-1][1];traffic+=queries[i-1][2]
            by[corpus,key,method,i].append((total/1e6,traffic))
    rng=np.random.default_rng(273247)
    out={}
    for corpus,intervals in (("isetrace",[0,1]),("squad",[0,1,3,6,11])):
        ids=sorted({r[2] for r in rows if r[1]==corpus})
        index=rng.integers(0,len(ids),(20000,len(ids)))
        for n in intervals:
            methods=sorted({r[3] for r in rows})
            values={}
            for method in methods:
                recs=[by[corpus,key,method,n] for key in ids]
                assert all(len(records)==3 for records in recs)
                times=np.array([median(rec[0] for rec in records) for records in recs])
                traffic=np.array([median(rec[1] for rec in records) for records in recs])
                values[method]=(times,traffic)
            ref=values["raw"][0]
            metrics={}
            for method,(times,traffic) in values.items():
                delta=times-ref
                draws=np.mean(delta[index],axis=1)
                metrics[method]={"p50_total_ms":float(np.median(times)), "mean_total_ms":float(times.mean()),
                    "mean_payload_bytes":float(np.mean(traffic)), "mean_delta_ms_vs_raw":float(delta.mean()),
                    "ci95":np.quantile(draws,[.025,.975]).tolist(),"ci97_5":np.quantile(draws,[.0125,.9875]).tolist(),
                    "faster_than_raw":int((delta<0).sum()),"episodes":len(ids)}
            out[f"{corpus}/{n}"]=metrics
    sizes={}
    for rep,method,*values in load("promotion-sizes.json" if prefix else "files.json"):
        sizes.setdefault(method,[]).append(values)
    raw=(json.dumps({"samples":out,"files":sizes},sort_keys=True,allow_nan=False,indent=2)+"\n").encode()
    (HERE/(prefix+"results.json")).write_bytes(raw)
    for group,ms in out.items():
        print(group, {m:round(v["p50_total_ms"],3) for m,v in ms.items()})
    for group in ("isetrace/1","squad/11"):
        print(group,out[group]["eager"])
if __name__=="__main__":
    main()

