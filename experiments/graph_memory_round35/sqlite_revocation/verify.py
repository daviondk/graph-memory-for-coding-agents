"""Independently verify stored physical sample membership, repeated reads and average costs."""
import gzip
import hashlib
import json
import math
import statistics
from pathlib import Path

D = Path(__file__).resolve().parent
def read(name):
    data = (D/name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)

def check():
    runs, plans, result = read("runs.json.gz"), read("plan.json"), read("results.json")
    assert len(runs) == 512 and len(set(plans["histories"])) == 64
    assert len({(r["trajectory"],r["method"],r["rep"]) for r in runs}) == 512
    assert hashlib.sha256((D/"runs.json.gz").read_bytes()).hexdigest() == result["runs"]
    assert all(r["reads"]==5 and 0<r["before_checkpoint_ms"]<=r["ms"] for r in runs)
    totals = [0,0]
    for h in plans["histories"]:
        a = [r for r in runs if r["trajectory"]==h]
        assert len(a)==8 and len({r["observed"] for r in a}) == 1
        for i,method in enumerate(("exact","before_read")):
            rs = [r for r in a if r["method"]==method]
            assert len(rs)==4 and len({r["tx"] for r in rs})==1
            totals[i]+=rs[0]["tx"]
    assert totals == [901,809]
    for i,method in enumerate(("exact","before_read")):
        per_trajectory=[statistics.median(r["ms"] for r in runs if r["trajectory"]==h and r["method"]==method) for h in plans["histories"]]
        assert math.isclose(statistics.mean(per_trajectory),result["summaries"]["ms"]["means"][i])
    return len(runs)
if __name__=="__main__": print(check())

