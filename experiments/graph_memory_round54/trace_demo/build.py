"""Materialize anonymized receipts and allowlisted paths; select examples before opening labels."""
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from serve import ROOT,state
SRC=ROOT.parent/"next_read"
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def digest(p):return sha256(p.read_bytes()).hexdigest()
def order(q):return sha256(("r54-trace-demo-v1|"+q).encode()).digest()
SCHEMA="""
CREATE TABLE episode(q TEXT PRIMARY KEY,seq INTEGER UNIQUE,repo TEXT,revision TEXT,task TEXT) WITHOUT ROWID;
CREATE TABLE path(q TEXT,h TEXT,name TEXT,PRIMARY KEY(q,h)) WITHOUT ROWID;
CREATE TABLE origin(q TEXT,h TEXT,strict INTEGER NOT NULL,PRIMARY KEY(q,h)) WITHOUT ROWID;
CREATE TABLE proposal(q TEXT,h TEXT,rank INTEGER,eligible INTEGER,previously_read INTEGER,PRIMARY KEY(q,rank)) WITHOUT ROWID;
CREATE TABLE candidate(q TEXT,h TEXT,ord INTEGER,proposed INTEGER,lexical INTEGER,repomap INTEGER,embed4 INTEGER,embed8 INTEGER,PRIMARY KEY(q,h)) WITHOUT ROWID;
CREATE TABLE receipt(q TEXT,h TEXT,first_line INTEGER,last_line INTEGER,text_sha256 TEXT,PRIMARY KEY(q,h)) WITHOUT ROWID;
"""
def build():
    seal=read(SRC/"fusion-seal.json");assert all(digest(SRC/k)==v for k,v in seal.items())
    explicit_seal=read(SRC/"explicit-seal.json");assert explicit_seal["decisions"]==digest(SRC/"explicit-decisions.json.gz")
    available=read(SRC/"demo-paths.json");explicit=read(SRC/"explicit-decisions.json.gz")
    ranks=read(SRC/"fusion-inputs.json.gz");fusion=read(SRC/"fusion-choices.json.gz")
    chosen={}
    for q in sorted(available,key=order):chosen.setdefault(available[q]["repo"],q)
    neutral=list(chosen.values())
    qids=neutral+[q for q in sorted(available,key=order) if q not in neutral]
    tokio=read(ROOT/"tokio-paths.json")
    assert not (available.keys() & tokio.keys())
    assert set(tokio)=={q for q,x in explicit.items() if x["repo"].lower()=="tokio-rs/tokio"}
    qids.extend(sorted(tokio,key=order))
    available.update(tokio)
    base_methods=("lexical","repomap","embed4","embed8");checks={}
    with TemporaryDirectory(dir=ROOT) as td:
        tmp=Path(td);main=sqlite3.connect(tmp/"trace.sqlite");main.row_factory=sqlite3.Row
        main.executescript(SCHEMA)
        for n,q in enumerate(qids):
            obs=explicit[q];maps=available[q];paths=maps["paths"];inp=ranks[q];rr=fusion[q]
            assert all(sha256((obs["repo"]+"\0"+v).encode()).hexdigest()==h for h,v in paths.items())
            assert obs["repo"]==maps["repo"] and obs["commit"]==maps["commit"]
            main.execute("INSERT INTO episode VALUES(?,?,?,?,?)",(q,n,obs["repo"],obs["commit"],obs["task"]))
            main.executemany("INSERT INTO path VALUES(?,?,?)",[(q,h,v) for h,v in sorted(paths.items())])
            opened=set(obs["opened"]);strict=set(obs["strict"]);allowed=inp["lexical_order"];raw=inp["proposals"]
            assert strict<=opened and not opened.intersection(allowed) and set(allowed)<=set(paths)
            assert len(raw)==len(set(raw)) and [h for h in raw if h in allowed]==obs["new_suggestions"]
            main.executemany("INSERT INTO origin VALUES(?,?,?)",[(q,h,int(h in strict)) for h in sorted(opened)])
            main.executemany("INSERT INTO proposal VALUES(?,?,?,?,?)",[(q,h,i,int(h in allowed),int(h in opened)) for i,h in enumerate(raw,1)])
            mm={m:{h:i for i,h in enumerate(inp["ranks"][m],1)} for m in base_methods}
            assert all(len(mm[m])==len(inp["ranks"][m]) for m in mm)
            for i,h in enumerate(allowed):
                pos=raw.index(h)+1 if h in raw else None
                main.execute("INSERT INTO candidate VALUES(?,?,?,?,?,?,?,?)",(q,h,i,pos,*[mm[m].get(h) for m in base_methods]))
            receipts=dict(obs["receipts"])
            for h,value in rr["receipts"].items():assert receipts.setdefault(h,value)==value
            for h,(lo,hi,sha) in sorted(receipts.items()):
                assert hi>=lo>=1 and len(sha)==64
                main.execute("INSERT INTO receipt VALUES(?,?,?,?,?)",(q,h,lo,hi,sha))
            checks[q]={k:obs["chosen"][src] for k,src in (("rrf","fusion"),("suggested","memory"),("confirmed","confirmed"))}
            checks[q].update(memory_rrf=rr["chosen"]["memory_four"],static_four=rr["chosen"]["static_four"])
            for method,h in checks[q].items():
                s=state(main,dict(q=q,method=method,version="1"));assert s["selected"]["id"]==h
                assert s["receipt"]==dict(zip(("first_line","last_line","text_sha256"),receipts[h]))
        main.commit();main.execute("VACUUM");main.close()
        # Only after every SQL choice has been checked do we open the independent labels.
        labels=read(SRC/"labels.json.gz");audit=sqlite3.connect(tmp/"audit.sqlite")
        audit.execute("CREATE TABLE required(q TEXT,h TEXT,PRIMARY KEY(q,h)) WITHOUT ROWID")
        audit.execute("CREATE TABLE reference(q TEXT,method TEXT,h TEXT,PRIMARY KEY(q,method)) WITHOUT ROWID")
        for q in qids:
            audit.executemany("INSERT INTO required VALUES(?,?)",[(q,h) for h in labels[q]])
            audit.executemany("INSERT INTO reference VALUES(?,?,?)",[(q,k,h) for k,h in checks[q].items()])
        audit.commit();audit.execute("VACUUM");audit.close()
        for file in ("trace.sqlite","audit.sqlite"):os.replace(tmp/file,ROOT/file)
    meta={"selection":"For the original 36 cases, minimum SHA256(r54-trace-demo-v1| + sample_id) per initial public repository first, then remaining sorted hashes. Append all 31 Tokio cases by the same digest. Supplement chosen after inspection to illustrate both directions; no episode filtered within any cohort.",
          "available":len(available),"initial_count":len(available)-len(tokio),"supplement":dict(cohort="tokio-rs/tokio",count=len(tokio),path_sha256=digest(ROOT/"tokio-paths.json")),"neutral_defaults":neutral,"ids":qids,"panel_size":len(explicit),"build_sources":{n:digest(SRC/n) for n in ("fusion-seal.json","explicit-seal.json","demo-paths.json","labels.json.gz")},
          "assets":{n:digest(ROOT/n) for n in ("trace.sqlite","audit.sqlite")} }
    (ROOT/"build.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf8");print(json.dumps(meta))
if __name__=="__main__":build()
