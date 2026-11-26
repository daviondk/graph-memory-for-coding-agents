"""Portable stdlib snapshot check; never modifies benchmark timings."""
from pathlib import Path
import hashlib
import json
import gzip
from statistics import median
D=Path(__file__).resolve().parent


def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)


def main():
    files=load(D/"manifest.json")["files"]
    assert all(hashlib.sha256((D/name).read_bytes()).hexdigest()==digest for name,digest in files.items())
    summary=load(D/"results.json")
    stages=load(D/"time-seal.json")
    totals={m:[0.,0.] for m in stages["methods"]}
    for s in summary["seeds"]:
        rows=load(D/f"warm-{s}.json.gz")
        assert len(rows)==2000
        for tr,hashes,record in rows.values():
            assert len(hashes)==4 and all(len(h)==64 for h in hashes)
            for m,reps in zip(stages["methods"],record):
                assert len(reps)==3 and all(len(v)==5 and min(v)>=0 and v[1]+v[2]+v[3]==v[4] for v in reps)
                totals[m][0]+=median(v[0] for v in reps)/1000
                totals[m][1]+=median(v[4] for v in reps)/1000
    n=summary["n_questions"]*len(summary["seeds"])
    for m,(cached,online) in totals.items():
        assert abs(cached/n-summary["means"][m][3])<1e-8
        assert abs(online/n-summary["means"][m][-1])<1e-8
    cold=load(D/"cold.json")["runs"]
    assert len(cold)==20
    for m in stages["methods"]:
        subset=[v for v in cold if v["mode"]==m]
        assert median(v["wall_ns"] for v in subset)/1e6==summary["cold_medians"][m]["wall_ms"]
    assert min(summary["eligible"],key=lambda m:summary["means"][m][-1])==summary["choice"]
    print("Verified",len(files),"files, 240000 warm calls, 20 measured processes")


if __name__=="__main__":
    main()
