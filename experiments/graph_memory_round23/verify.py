"""Verify published artifacts and per-question totals without a network, GPU, or external data."""
from pathlib import Path
import hashlib
import gzip
import json
import sqlite3

ROOT=Path(__file__).resolve().parent
def load(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(r, f, h):
    p=(r/f).resolve()
    assert p.is_relative_to(r.resolve()) and sha(p)==h, p
def by_hashes(r, index):
    for f,h in load(r/index)["files"].items():check(r,f,h)
def verify():
    studies=load(ROOT/"release.json")["completed"]
    for name in studies:
        d=ROOT/name
        assert (d/"REPORT_RU.md").is_file(),name
        p=d/"MANIFEST_SHA256.json"
        if not p.exists():p=d/"manifest.json"
        if p.exists():
            manifest=load(p);files=manifest.get("files",manifest)
            for f,h in files.items():check(d,f,h)
    read=ROOT/"read_causes";results=load(read/"results.json");by_hashes(read,"receipt-lock.json")
    locks=load(read/"inputs.json");check(read,"registry.sqlite",locks["registry_sha"])
    c=sqlite3.connect((read/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    assert c.execute("pragma integrity_check").fetchone()==("ok",)
    assert c.execute("select count(*),count(distinct t) from address").fetchone()==(72184,1207)
    c.close()
    assert results["verified_bare_query_policy_rows"]==4000
    check(read,"per-query.json.gz",results["per_query_sha256"])
    rec=load(read/"per-query.json.gz")["questions"];assert len(rec)==2000
    for k,v in results["summaries"].items():
        vv=[r["values"][k] for r in rec.values()]
        assert sum(x[0] for x in vv)==v["hits"] and sum(x[1] for x in vv)==v["intact"]
        assert max(x[3] for x in vv)<=int(k.rsplit("/",1)[1])
    for name,lock in (("field_first","read-lock.json"),("address_open","read-lock.json"),("receiver_merge","receiver-lock.json"),("boundary","extend-lock.json")):
        d=ROOT/name;by_hashes(d,lock)
    for name,link,k in (("field_first","per_query","summaries"),("address_open","per_query","all"),("boundary","outcomes","summaries")):
        d=ROOT/name;out=load(d/"results.json");check(d,"per-query.json.gz",out[link])
        rows=load(d/"per-query.json.gz")["rows"];assert rows.keys()==rec.keys()
        for key,val in out[k].items():
            assert sum(r.get("values",r.get("outcomes"))[key][0] for r in rows.values())==val["hits"]
    d=ROOT/"receiver_merge";out=load(d/"results.json");check(d,"per-query.json.gz",out["outcomes_sha"])
    assert out["hits"]=={"receiver":1654,"sender":1671,"receiver_read":218,"sender_read":222}
    d=ROOT/"marginal_transfer";v=load(d/"results.json")
    check(d,"per-query.json.gz",v["values_sha"]);check(d,"actions.json.gz",load(d/"forecast-seal.json")["predictions"])
    rows=load(d/"per-query.json.gz")["rows"]
    assert len(rows)==661 and sum(r["base"][0] for r in rows.values())==v["basehits"]
    for k,s in v["summaries"].items():assert sum(r["values"][k][0] for r in rows.values())==s["hits"]
    assert all(x["unequal_final"]==0 for x in load(d/"cost-results.json")["pairs"].values())
    d=ROOT/"published_reader"
    for mode in ("test","test-equal-spend"):
        out=load(d/(mode+"-results.json"));rows=load(d/(mode+"-outcomes.json.gz"))
        check(d,mode+"-outcomes.json.gz",out["per_query"])
        assert len(rows)==len({r["t"] for r in rows})==192
        for method,metrics in out["measures"].items():
            assert abs(sum(r["scores"][method]["full"] for r in rows)/len(rows)-metrics["full"])<1e-10
        if mode.endswith("equal-spend"):
            assert all(r["scores"]["verbatim_core"]["tokens"]==r["cap"] for r in rows)
            assert all(x["tokens"]<=r["cap"] for r in rows for x in r["scores"].values())
    return len(studies)
if __name__=="__main__": print("verified completed studies:",verify())
