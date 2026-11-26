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

    outcomes=read("calibration_transfer/outcomes.json.gz")
    thresholds=read("cost_to_support/thresholds.json.gz")
    assert len(outcomes)==2000 and outcomes.keys()==thresholds.keys()
    totals=[0,0]
    for q,r in outcomes.items():
        assert thresholds[q]["trajectory"]==r["t"]
        for i,seed in enumerate(("13","17","29","37","41")):
            for j,method in enumerate(("original_R33","oof_3894")):
                v=r["seeds"][seed][method][0]
                assert (thresholds[q]["costs"][i][j]<=2048)==v
                totals[j]+=int(v)
    assert totals==[8046,8089],totals
    native=read("native_prefix/outcomes.json.gz")
    assert native.keys()==outcomes.keys()
    assert [sum(r["seeds"][s][k][0] for r in native.values() for s in ("13","17")) for k in ("oof_3894","full_rgcn","wo_chunk_adjacency")]==[3239,3137,3163]
    states=read("deferred_revocation/outcomes.json.gz")
    assert len(states)==len({(r["q"],r["cut"]) for r in states})==8000
    assert all(r["arms"]["exact"]==r["arms"]["lazy_read"] for r in states)
    mid=[r for r in states if r["cut"]==50 and not r["pilot"] and r["eligible"]]
    assert len(mid)==901 and [sum(r["arms"][k][0] for r in mid) for k in ("exact","periodic4","pending4","append")]==[752,748,736,725]
    schedules=read("read_frequency/results.json")
    assert schedules["eager_batches"]==4666 and schedules["schedules"]["actual"]["total"]["batches"]==2630
    assert schedules["schedules"]["actual"]["total"]["deleted_rows"]==8015
    primary=read("sqlite_revocation/runs.json.gz")
    replicate=read("sqlite_replication/runs.json.gz")
    assert len(primary)==512 and len(replicate)==1024
    assert set(r["trajectory"] for r in primary).isdisjoint(r["trajectory"] for r in replicate)
    for runs in (primary,replicate):
        observed={}
        for r in runs:
            assert r["reads"]==5 and observed.setdefault(r["trajectory"],r["observed"])==r["observed"]
        assert len(observed)==64
    crash=read("recovery/results.json")["groups"]
    assert crash["post"]["cases"]==128 and crash["post"]["methods"]["naive"]["next_mismatch"]==54
    assert crash["post"]["methods"]["replay"]["wrong_reads"]==crash["uncommitted_first"]["methods"]["replay"]["wrong_reads"]==0
    assert read("live_demo/browser-receipt.json")["states"]==24
    assert set(release["completed"])==set(release["manifests"])
    return len(release["completed"])

if __name__=="__main__":print("Verified studies",verify())
