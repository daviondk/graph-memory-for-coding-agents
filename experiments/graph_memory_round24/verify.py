"""Offline validation of the four completed studies and the interactive snapshot."""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
ROOT=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def contents(root,files):
    for name,digest in files.items():
        p=(root/name).resolve()
        assert p.is_relative_to(root.resolve()) and sha(p)==digest,p
def verify():
    for name in ("marginal_mmr","inspection_demo"):
        d=ROOT/name
        fp=next(p for p in (d/"manifest.json",d/"MANIFEST_SHA256.json") if p.exists())
        m=read(fp);contents(d,m.get("files",m))
    d=ROOT/"attainable_open";a=read(d/"results.json")
    assert sha(d/"per-query.json.gz")==a["per_query"] and sha(d/"PROTOCOL_RU.md")==a["protocol"] and sha(d/"ceiling.py")==a["code"]
    for tag,rows in read(d/"per-query.json.gz").items():
        s=a["summary"][tag]
        assert len(rows)==s["n"] and sum(r["base"] for r in rows.values())==s["base"]
        assert sum(r.get("legal_successes",0)>0 for r in rows.values())==s["legal_window"]
    d=ROOT/"frontier_open";s=read(d/"action-lock.json");contents(d,s["files"])
    assert sha(d/"PROTOCOL_RU.md")==s["plan"] and sha(d/"routes.py")==s["code"]
    scores=read(d/"results.json");assert sha(d/"per-query.json.gz")==scores["outcomes"]
    audit=read(d/"mmr-results.json");assert sha(d/"mmr-outcomes.json.gz")==audit["scores"]
    for tag,rows in read(d/"per-query.json.gz")["corpora"].items():
        summary=scores["results"][tag];assert len(rows)==summary["n"] and summary["unequal_matched_cost"]==0
        for name,record in summary["summary"].items():
            assert sum(r["scores"][name][0] for r in rows.values())==record["hits"]
            assert max(r["scores"][name][3] for r in rows.values())<=256
        assert all(r["scores"]["right_edge_matched"][3]==r["scores"]["first_positive_matched"][3] for r in rows.values())
    for tag,rows in read(d/"mmr-outcomes.json.gz").items():
        for name,record in audit["results"][tag]["summary"].items():
            assert sum(r["scores"][name][0] for r in rows.values())==record["hits"]
        assert all(r["scores"]["edge_eq"][2]==r["scores"]["mmr_eq"][2] for r in rows.values())
    d=ROOT/"inspection_demo";b=read(d/"browser-receipt.json")
    assert b["cases"]==19 and all(v["verified_modes"]==114 for v in b["modes"].values())
    db=sqlite3.connect((d/"inspection.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    assert db.execute("pragma integrity_check").fetchone()==("ok",);db.close()
    return 4
if __name__=="__main__":print("verified studies",verify())
