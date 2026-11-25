"""Recompute reported counts across separately produced studies and validate the stored demo."""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
D=Path(__file__).resolve().parent

def read(name):
    p=D/name;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)

def verify():
    ret=read("incremental_binding/prefix-outcomes.json.gz")
    assert len(ret)==96 and sum(len(v["records"]) for v in ret)==383
    seq=[r for v in ret for r in v["records"] if not r["last"]]
    assert len(seq)==287
    def mismatch(method):
        return sum(r["sha"]!=r["arms"][method]["sha"] for r in seq)
    assert [mismatch(k) for k in ("counted","append","retrospective")]==[0,175,61]
    assert all(r["sha"]==r["arms"]["counted"]["sha"] for t in ret for r in t["records"])
    costs=read("incremental_binding/cost-resolution-results.json")
    assert costs["blocks"]==864 and costs["zero_blocks"]==0
    rank=read("incremental_binding/readout-outcomes.json.gz")
    other=[r for r in rank if not r["pilot"]];assert len(other)==1845
    assert len({r["t"] for r in other})==1111
    assert [sum(r["arms"][a]["fs"] for r in other) for a in ("exact","append","half","shuffled")]==[1456,1376,1435,1374]
    dyn=read("factorized_provenance/by-query.json.gz")
    assert len(dyn)==2000 and all(r["match"]["prefix"] and r["match"]["skip"] for r in dyn)
    assert max(r["error"] for r in dyn)<1e-10
    sizes=read("factorized_provenance/results.json")["size"]
    assert [sizes[k]["bytes"] for k in ("flat","packed")]==[5025792,3190784]
    sys.path.insert(0,str(D/"provenance_demo"))
    from store import connect,revisions
    with connect() as db:
        assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
        scene=revisions(db,"traj_07048cf98d08c4a5",14,19,59)
        assert [r["cause"] for r in scene["evidence"]]==["match","ambiguous"] and scene["evidence"][1]["other"]==19
        assert scene["evidence"][0]["value"]==scene["evidence"][1]["value"]
    assert read("provenance_demo/offline-receipt.json")["offline_all_383_checkpoints_rechecked"]
    for s in ("binding_refit","handoff"):
        m=read(s+"/MANIFEST_SHA256.json")
        for name,h in m.items():assert hashlib.sha256((D/s/name).read_bytes()).hexdigest()==h,(s,name)
    return {"prefixes":383,"exact_vs_append_frozen_n":len(other),"reader_queries":len(dyn),"demo_scene":scene,
            "submanifests":["binding_refit","handoff"]}

if __name__=="__main__":print(json.dumps(verify(),ensure_ascii=False))
