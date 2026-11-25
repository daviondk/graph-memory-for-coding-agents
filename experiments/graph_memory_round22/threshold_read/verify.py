"""Portable verifier: replay numeric outputs and recalculate paired comparisons and query totals."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import numpy as np

from operators import index, suffix_bounds, read
HERE=Path(__file__).resolve().parent
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def assert_close(a,b):assert abs(a-b)<1e-9,(a,b)
def digest(ids):return hashlib.sha256(np.asarray(ids,dtype="<i8").tobytes()).hexdigest()
def verify():
    base=load(HERE/"inputs.json");observed={r["q"]:r for r in load(HERE/"per-query.json.gz")}
    mem=load(HERE/"results.json")
    sql=load(HERE/"sqlite-results.json");native=load(HERE/"native-results.json")
    raw_sql={r["q"]:r for r in load(HERE/"sqlite-queries.json.gz")};low={r["q"]:r for r in load(HERE/"native-checks.json.gz")}
    assert set(raw_sql)==set(low)==set(observed)
    for doc in (load(HERE/"measurement-seal.json"),sql,native):
        assert all(sha(HERE/k)==v for k,v in doc["files"].items())
    assert mem["seal"]==sha(HERE/"measurement-seal.json")
    complete=set()
    for name,receipt in base["shards"].items():
        p=HERE/name;assert sha(p)==receipt["sha"]
        for row in load(p):
            ix=index(row["prior"],row["costs"]);sig=np.asarray(row["signal"]);up=suffix_bounds(sig)
            for q in row["queries"]:
                h=q["q"];assert h not in complete;complete.add(h)
                assert observed[h]["t"]==raw_sql[h]["t"]==low[h]["t"]==row["t"]
                order=np.asarray(q["order"]);n=len(order)
                assert n==observed[h]["n"]==raw_sql[h]["n"]==low[h]["n"]
                for pol in ("prefix","skip"):
                    e=q["expected"][pol];rec=observed[h]["arms"][pol]
                    assert rec["expect_hash"]==digest(e) and rec["tokens"]<=2048 and rec["tokens"]==sum(ix.costs[e]) and rec["nodes"]==len(e)
                    for method in ("vector","heap","one","two"):
                        seq,ctr=read(method,order,sig,up,ix,2048,pol)
                        assert seq==e and ctr==rec["counts"][method]
                    assert raw_sql[h]["rows"][pol+"/vector"]==n
                    scanned=rec["counts"]["one"]["dense_cursor"]
                    assert raw_sql[h]["rows"][pol+"/stream"]==min(n,16*((scanned+15)//16))
                    assert low[h]["counters"][pol+"/stream"]["rows"]==scanned
                    assert low[h]["counters"][pol+"/vector"]["rows"]==low[h]["counters"][pol+"/heap"]["rows"]==n
    assert len(complete)==2000 and len(set(r["t"] for r in observed.values()))==1207
    for d,raw,field in ((sql,raw_sql,"rows"),(native,low,"counters")):
        for arm in next(iter(raw.values()))[field]:
            if field=="rows":
                assert sum(v[field][arm] for v in raw.values())==d["summary"][arm]["rows"]
            else:
                assert all(sum(v[field][arm][k] for v in raw.values())==value for k,value in d["totals"][arm].items())
    for filename,result_name,native_time in (("timings.json.gz","results.json",False),("sqlite-timing.json.gz","sqlite-results.json",False),("native-times.json.gz","native-results.json",True)):
        logs=load(HERE/filename);r=load(HERE/result_name);groups=defaultdict(list)
        for v in logs:groups[v["q"]].append(v)
        assert len(groups)==256 and all(sorted(x["rep"] for x in vals)==list(range(7)) for vals in groups.values())
        for clock in (("inside_ns","outside_ns") if native_time else ("ns",)):
            for arm in logs[0][clock]:
                medians=[statistics.median(v[clock][arm] for v in vals)/1000 for vals in groups.values()]
                if native_time:stat=r["times"][clock+"/"+arm]
                elif filename=="timings.json.gz":
                    pol,method=arm.split("/");stat=r["operator"][pol][method]
                else:stat=r["summary"][arm]
                assert_close(np.median(medians),stat["median_us"]);assert_close(np.quantile(medians,.95),stat["p95_us"])
    assert load(HERE/"native-results.json")["real_comparisons"]==20000
    assert load(HERE/"edge-cases.json")["method_policy_comparisons"]==6776
    print("Verified 2000 source questions, all 16000 ordered Python selections, all SQL/native counts and all latency medians/p95 from 3 x 1792 paired blocks.")
def manifest():
    allowed={".md",".py",".cpp",".gz",".json"}
    return {p.relative_to(HERE).as_posix():sha(p) for p in sorted(HERE.rglob("*")) if p.is_file() and p.suffix in allowed and p.name!="MANIFEST_SHA256.json" and "__pycache__" not in p.parts}
if __name__=="__main__":
    verify()
    path=HERE/"MANIFEST_SHA256.json"
    if "--seal" in sys.argv:path.write_text(json.dumps(manifest(),sort_keys=True,separators=(",",":"))+"\n",encoding="utf8")
    if path.exists():assert load(path)==manifest()

