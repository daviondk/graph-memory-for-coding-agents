"""Recompute every source-removal aggregate from portable raw observations."""
import gzip,hashlib,json,math
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    metrics=read(D/"results.json");seal=read(D/"schedule-seal.json")
    assert sha(D/"observations.json.gz")==metrics["observations"] and sha(D/"schedule.json.gz")==seal["frozen"]
    data=read(D/"observations.json.gz");schedule=read(D/"schedule.json.gz");rows=[r for v in data.values() for r in v["rows"]]
    assert len(rows)==metrics["sources"];assert len(schedule)==len(data)==metrics["queries"]
    for q,v in data.items():
        assert [r["source"] for r in v["rows"]]==schedule[q]["sources"]
        for r in v["rows"]:
            assert r["changed"]==(r["full_packet"]!=schedule[q]["packet"])
            assert r["needs"]["certificate"]==bool(r["selected_dep"] or r["barrier_dep"])
            if not r["needs"]["certificate"]:assert not r["changed"]
            assert all(len(t)==3 and min(t)>0 for t in r["timings"].values())
    assert metrics["exact_cached"]==sum(not r["needs"]["certificate"] for r in rows)
    assert metrics["changed"]==sum(r["changed"] for r in rows)
    ratio=sum(sum(r["timings"]["full"]) for r in rows)/sum(sum(r["timings"]["certificate"]) for r in rows)
    assert math.isclose(ratio,metrics["full_vs_cert_ratio"],rel_tol=1e-12)
    if (D/"manifest.json").exists():
        for name,h in read(D/"manifest.json")["files"].items():assert sha(D/name)==h,name
    print(len(rows),metrics["exact_cached"],round(ratio,4))
if __name__=="__main__":main()

