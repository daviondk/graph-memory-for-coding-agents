"""Summarize interleaved latency measurements with a paired article bootstrap."""
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median
import numpy as np
HERE=Path(__file__).resolve().parent
def summarize():
    file=HERE/"service-times.json.gz"
    assert hashlib.sha256(file.read_bytes()).hexdigest()==json.loads((HERE/"service-receipt.json").read_bytes())["times"]
    rows=json.loads(gzip.decompress(file.read_bytes()))
    queries=sorted({r[1] for r in rows});modes=sorted({r[3] for r in rows})
    assert len({r[2] for r in rows})==len(queries)==24
    result={}
    for mode in modes:
        selected=[r for r in rows if r[3]==mode]
        def latencies(m,q):return [r[7]/1e6 for r in rows if r[3]==m and r[1]==q]
        assert all(len(latencies(mode,q))==2 for q in queries)
        typical=np.array([median(latencies(mode,q)) for q in queries])
        direct=np.array([median(latencies("direct",q)) for q in queries])
        indices=np.random.default_rng(28211).integers(24,size=(20000,24))
        delta=np.median((typical-direct)[indices],axis=1)
        lat=[r[7]/1e6 for r in selected]
        result[mode]={"episodes":len(selected),"opened":sum(r[4] for r in selected),"forward":sum(r[5] for r in selected),
                     "tokens":sum(r[6] for r in selected),"latency_ms_p50":median(lat),"latency_ms_p95":float(np.quantile(lat,.95)),
                     "paired_median_ms_vs_direct":median(typical-direct),"ci95":np.quantile(delta,[.025,.975]).tolist()}
    return result
if __name__=="__main__":
    (HERE/"service-results.json").write_text(json.dumps(summarize(),sort_keys=True,indent=2)+"\n",encoding="utf8")
