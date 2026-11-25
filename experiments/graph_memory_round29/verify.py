"""Check all included study seals and recompute main observed contrasts."""
import gzip,hashlib,json,math,runpy
from pathlib import Path
from statistics import mean
ROOT=Path(__file__).resolve().parent
def read(relative):
    p=ROOT/relative
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def verify():
    release=read("release.json")
    for n,h in release["manifests"].items():
        base=ROOT/n;p=next(p for p in (base/"manifest.json",base/"MANIFEST_SHA256.json") if p.is_file())
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        assert digest(p)==h,p
        obj=json.loads(p.read_bytes());files=obj.get("files",obj)
        if isinstance(files,list):files={r["name"]:r.get("sha",r.get("sha256")) for r in files}
        assert set(files)=={f.relative_to(base).as_posix() for f in base.rglob("*") if f.is_file() and "__pycache__" not in f.parts and f!=p}
        for relative,d in files.items():
            t=(base/relative).resolve()
            assert t.is_relative_to(base) and digest(t)==(d["sha256"] if isinstance(d,dict) else d),t
    assert set(release["completed"])==set(release["manifests"])
    a=read("pareto_cache/results.json")
    assert a["strict"]==3456 and a["contrasts"]["all"]["64"]["rescued"]==161 and a["contrasts"]["all"]["64"]["regressed"]==0
    assert a["cache_stores"]["pareto64"]["rows"]==a["cache_stores"]["raw64"]["rows"]==6144
    tree=read("direct_frontier/results.json");assert tree["original_candidate_spans"]==6677914 and tree["records"]==3059
    assert read("multi_retraction/results.json")["main_cases"]==576
    routes=read("native_revisions/routes.json.gz");out=read("native_revisions/outcomes.json.gz");summary=read("native_revisions/results.json")
    assert len(routes)==len(out)==514
    for k in (0,51,171,257,514):
        for method in next(iter(routes.values()))["rank"]:
            chosen=[out[q]["cold" if r["rank"][method]<k else "old"] for q,r in routes.items()]
            expected=summary["scheduled"][str(k)]["mean"][method]
            assert all(math.isclose(100*mean(row[i] for row in chosen),v,abs_tol=1e-9) for i,v in enumerate(expected))
    records=read("revision_reader/forecasts.json.gz");assert sum(r["old"]["calls"]+r["new"]["calls"] for r in records.values())==1096
    results=read("witness_algebra/results.json");assert runpy.run_path(str(ROOT/"witness_algebra/check.py"))["verify"]()==results
    return len(release["completed"])
if __name__=="__main__":print("Verified studies",verify())
