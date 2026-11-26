"""Validate released study files and headline quantities using the measured rows."""
import gzip,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(path):
    p=ROOT/path;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def verify():
    release=read("release.json")
    for name,wanted in release["manifests"].items():
        base=ROOT/name
        p=next(p for p in (base/"manifest.json",base/"MANIFEST_SHA256.json") if p.is_file())
        sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
        assert sha(p)==wanted,p
        content=json.loads(p.read_bytes());files=content.get("files",content)
        if isinstance(files,list):files={f.get("name",f.get("file")):f.get("sha",f.get("sha256")) for f in files}
        assert set(files)=={f.relative_to(base).as_posix() for f in base.rglob("*") if f.is_file() and "__pycache__" not in f.parts and f!=p}
        for rel,expected in files.items():
            file=(base/rel).resolve();dig=expected["sha256"] if isinstance(expected,dict) else expected
            assert file.is_relative_to(base) and sha(file)==dig,file

    current=read("live_reader/native-outcomes.json.gz")
    assert len(current)==len({(r["q"],r["cut"]) for r in current})==8000
    assert not any(r["changed_fs"] for r in current)
    half=[r for r in current if r["cut"]==50 and r["eligible"] and not r["pilot"]]
    assert len(half)==901 and len({r["t"] for r in half})==657
    assert [sum(r["arms"][m][0] for r in half) for m in ("exact","previous")]==[752,732]
    forecast=read("live_reader/outcomes.json.gz")
    half=[r for r in forecast if r["cut"]==50 and r["eligible"] and not r["pilot"]]
    assert [sum(r["arms"][m][0] for r in half) for m in ("append","metadata","dense")]==[725,708,682]
    raw=read("live_reader/independent.json")
    assert raw["states"]==96 and raw["total_selections"]==raw["exact_selections"]==420
    cases=read("external_transfer/strong/test-outcomes.json.gz")
    assert len(cases)==214 and len({r["repo"] for r in cases.values()})==69
    assert [sum(r["arms"][m][0] for r in cases.values()) for m in ("dense_state","union_cost","frozen_role1")]==[96,101,95]
    controls=read("cost_push/test-outcomes.json.gz")
    assert len(controls)==2000 and all(r["arms"]["R33"][0]==r["arms"]["cost_log_0.03"][0] for r in controls.values())
    assert read("cost_push/audit.json")["min_bound_minus_realized"]>=0
    seeds=[read(f"native_checkpoint/outcomes-{s}.json.gz") for s in [13,17]]
    assert set(seeds[0])==set(seeds[1]) and len(seeds[0])==2000
    assert [sum(r[i][0] for seed in seeds for r in seed.values()) for i in (1,2,3)]==[3219,3137,3163]
    auc=read("strong_reader_controls/auc.json")["panels"]["all5"]["means_pct"]
    assert math.isclose(auc["cost"][1]-auc["frozen"][1],0.631,abs_tol=1e-8)
    assert read("reader_demo/browser-receipt.json")["oracle_states"]==320
    assert read("reader_cost/summary.json")["queries"]==96
    assert set(release["completed"])==set(release["manifests"])
    return len(release["completed"])

if __name__=="__main__":print("Verified studies",verify())
