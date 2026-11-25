"""Offline check of the two materialization studies and reported timing summaries."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import fmean, median
ROOT=Path(__file__).resolve().parent

def read(name):
    p=ROOT/name
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)

def check(name,expected):
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name

def verify():
    known={}
    for prefix in ("","promotion-"):
        receipt=read(prefix+"receipt.json")
        check(prefix+"times.json.gz",receipt["times"])
        check("plan.json" if not prefix else "promotion-lock.json",receipt["plan"] if not prefix else receipt["lock"])
        if prefix:
            check("resident-heap.json",receipt["heap"])
            check("promotion-sizes.json",receipt["sizes"])
        else:
            check("files.json",receipt["files"])
        records=read(prefix+"times.json.gz")
        assert len(records)==receipt["runs"]==2592
        assert sum(len(r[-1]) for r in records)==receipt["answers"]==11232
        assert len({r[2] for r in records})==144
        groups=defaultdict(list)
        for rep,corpus,ident,method,ingest,queries in records:
            assert len(queries)==(1 if corpus=="isetrace" else 11)
            elapsed=ingest;traffic=0
            groups[corpus,method,0,ident].append((elapsed/1e6,traffic))
            for i,(q,ns,amount,winner) in enumerate(queries,1):
                assert known.setdefault((ident,q),winner)==winner
                elapsed+=ns;traffic+=amount
                groups[corpus,method,i,ident].append((elapsed/1e6,traffic))
        for group,methods in read(prefix+"results.json")["samples"].items():
            corpus,n=group.split("/")
            for method,stats in methods.items():
                sets=[rows for (c,m,k,g),rows in groups.items() if (c,m,k)==(corpus,method,int(n))]
                assert len(sets)==stats["episodes"] and all(len(s)==3 for s in sets)
                times=[median(t for t,b in s) for s in sets]
                raw=[median(b for t,b in s) for s in sets]
                assert abs(median(times)-stats["p50_total_ms"])<1e-9
                assert abs(fmean(times)-stats["mean_total_ms"])<1e-9
                assert abs(fmean(raw)-stats["mean_payload_bytes"])<1e-9
    assert len(known)==624
    return len(known)
if __name__=="__main__":
    print("Verified distinct queries",verify())

