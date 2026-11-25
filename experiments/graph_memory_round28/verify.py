"""Verify frozen files and independently reconstruct headline statistics."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from statistics import mean
ROOT=Path(__file__).resolve().parent
def read(path):
    p=ROOT/path
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)
def close(x,y):return math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-10)
def verify():
    release=read("release.json")
    for name,expected in release["manifests"].items():
        base=ROOT/name
        p=next(p for p in (base/"manifest.json",base/"MANIFEST_SHA256.json") if p.is_file())
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        assert digest(p)==expected,(p,expected)
        contents=json.loads(p.read_bytes());files=contents.get("files",contents)
        if isinstance(files,list):files={x["name"]:x.get("sha256",x.get("sha")) for x in files}
        for relative,sha in files.items():
            path=(base/relative).resolve()
            assert path.is_relative_to(base) and digest(path)==sha,path
        actual={v.relative_to(base).as_posix() for v in base.rglob("*") if v.is_file() and "__pycache__" not in v.parts and v!=p}
        assert actual==set(files),(name,actual.symmetric_difference(files))
    assert set(release["completed"])==set(release["manifests"])
    d=read("revoked_evidence/decisions.json.gz");s=read("revoked_evidence/results.json")
    assert sum(x["same_source"] for x in d.values())==s["same_address"]==28
    assert len(d)==96 and sum(x["candidates"] for x in d.values())==6677914
    q=read("revoked_evidence/qa-outcomes.json.gz")
    assert sum(x["gold_in_residual"] for x in q.values())==10
    for m in s["metrics"]:
        for i,v in enumerate(s["metrics"][m]):assert close(v,100*mean(x["answers"][m][i] for x in q.values()))
    grouped=read("stable_groups/outcomes.json.gz");m=read("stable_groups/results.json")
    for state,table in grouped.items():
        for mode,metrics in m["states"][state]["means"].items():
            for field,value in metrics.items():assert close(value,mean(row[mode][field] for row in table.values()))
    trigger=read("read_trigger/outcomes.json.gz")["online"];aggregate=read("read_trigger/results.json")["results"]["online"]["summary"]
    for policy,rows in trigger.items():
        assert len(rows)==288 and sum(r[1] for r in rows)==aggregate[policy]["opened"]
        assert close(100*mean(r[2] for r in rows),aggregate[policy]["f1"])
    times=read("read_trigger/service-times.json.gz");service=read("read_trigger/service-results.json")
    assert len(times)==240 and sum(r[5] for r in times)==2154
    for mode,rec in service.items():
        assert sum(r[6] for r in times if r[3]==mode)==rec["tokens"]
    storage=read("logit_control/results.json");assert storage["strict_comparisons"]==28626
    db=(ROOT/"update_demo/sky.sqlite")
    assert db.stat().st_size==storage["storage_per_arm"]["sky"]==110592
    with sqlite3.connect(db.as_uri()+"?mode=ro",uri=True) as con:
        assert con.execute("pragma integrity_check").fetchone()==("ok",)
        assert sum(con.execute("select count(*) from "+t).fetchone()[0] for t in ("pre","suf"))==3059
    assert read("update_demo/browser-receipt.json")["interactive_checks"]==9
    assert read("sentence_answers/results.json")["n"]==576
    assert read("observed_symbol_read/swe-results.json")["scored"]==84
    assert read("observed_symbol_read/loc-results.json")["scored"]==40
    return len(release["completed"])
if __name__=="__main__":print("Verified studies",verify())
