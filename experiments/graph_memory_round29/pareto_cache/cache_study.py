"""Compare write policies at identical K and an identical exact window-logit fallback."""
from collections import defaultdict
from pathlib import Path
from time import perf_counter_ns as now
import random
import sqlite3
import sys
import numpy as np
D=Path(__file__).resolve().parent;PRE=D.parent/"multi_retraction";sys.path.insert(0,str(PRE))
from multiban_design import PRIVATE,read,save,sha,pack
from store import state,SCHEMA
from measure import rank_sql,flattened,better,scan_window
ARMS=("raw8","pareto8","raw64","pareto64")

def init():
    p,cases,old,logs,memory=state()
    protocol={"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(Path(__file__)),"source":sha(PRE/"measurement-seal.json"),"arms":list(ARMS)}
    f=D/"plan.json"
    if f.exists():assert read(f)==protocol
    else:save(f,protocol)
    dest=PRIVATE/"cache"/sha(f);dest.mkdir(parents=True,exist_ok=True)
    return p,old,logs,memory,dest

def build():
    p,old,logs,memory,dest=init()
    if (D/"build-seal.json").exists():return
    source=sqlite3.connect(old/"full.sqlite");source.execute("ATTACH DATABASE ? AS pr",(str(memory/"pareto.sqlite"),))
    sizes={}
    for arm in ARMS:
        path=dest/(arm+".sqlite")
        if path.exists():raise FileExistsError(path)
        db=sqlite3.connect(path);db.execute("CREATE TABLE r "+SCHEMA);table="main" if arm.startswith("raw") else "pr";k=8 if arm.endswith("8") else 64
        count=0;t=now()
        for ix,q in enumerate(p["qids"]):
            rows=source.execute("SELECT q,score,ord,lo,hi FROM "+table+".r WHERE q=? ORDER BY score DESC,ord LIMIT ?",(ix,k)).fetchall()
            assert len(rows)==k
            db.executemany("INSERT INTO r VALUES (?,?,?,?,?)",rows);count+=len(rows)
        db.commit();elapsed=now()-t
        assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
        db.close();sizes[arm]={"rows":count,"bytes":path.stat().st_size,"build_ns":elapsed,"sha":sha(path)}
    source.close();save(D/"build-seal.json",{"plan":sha(D/"plan.json"),"stores":sizes})

def query(db,arm,ix,bans):
    row=db.execute(rank_sql(arm,len(bans)),(ix,*flattened(bans))).fetchone()
    if row is not None:return row,[0,0,0,1,0]
    winner=None;blobs=0;windows=0;bounds=0
    for s,o,l,h,w in db.execute("SELECT score,ord,lo,hi,w FROM bounds.r WHERE q=? ORDER BY score DESC,ord",(ix,)):
        bounds+=1;upper=(s,o,l,h)
        if not better(upper,winner):break
        if all(h<=a or l>=b for a,b in bans):candidate=upper
        else:
            data=db.execute("SELECT b FROM zip.r WHERE q=? AND w=?",(ix,w)).fetchone()[0]
            blobs+=len(data);windows+=1;candidate=scan_window(data,w,bans)
        if better(candidate,winner):winner=candidate
    return winner,[1,blobs,windows,2+windows,bounds]

def main():
    p,old,logs,memory,dest=init();build();built=read(D/"build-seal.json")
    db=sqlite3.connect(":memory:")
    for arm,path in [(a,dest/(a+".sqlite")) for a in ARMS]+[(a,logs/(a+".sqlite")) for a in ("bounds","zip")]:
        db.execute("ATTACH DATABASE ? AS "+arm,(str(path),));db.execute(f"PRAGMA {arm}.cache_size=-32768")
    db.execute("PRAGMA query_only=1");db.execute("BEGIN")
    parents=read(PRE/"predictions.json.gz");counts={};work=[];strict=0
    for ix,q in enumerate(p["qids"]):
        counts[q]={}
        for cond,ref in parents[q].items():
            bans=ref["ban"];row={}
            for arm in ARMS:
                found,cost=query(db,arm,ix,bans);assert pack(found)==pack(ref["answer"])
                row[arm]=cost;strict+=1
            for k in (8,64):
                assert row["pareto"+str(k)][0]<=row["raw"+str(k)][0]
                if row["pareto"+str(k)][0]==row["raw"+str(k)][0]:
                    assert row["pareto"+str(k)]==row["raw"+str(k)]
            if "-" in cond:
                counts[q][cond]=row
                if q in p["panel"]:work.append((q,ix,cond,bans))
    for q,ix,cond,bans in work:
        for arm in ARMS:query(db,arm,ix,bans)
    times=[];rng=random.Random(29914)
    for rep in range(18):
        seq=work.copy();rng.shuffle(seq)
        for q,ix,cond,bans in seq:
            methods=list(ARMS);rng.shuffle(methods)
            for arm in methods:
                t=now();found,r=query(db,arm,ix,bans);b=pack(found);ns=now()-t
                times.append([q,cond,arm,rep,ns])
    db.execute("COMMIT");db.close()
    save(D/"costs.json.gz",counts);save(D/"latency.json.gz",times)
    save(D/"measurement-seal.json",{"plan":sha(D/"plan.json"),"build":sha(D/"build-seal.json"),"costs":sha(D/"costs.json.gz"),
         "latency":sha(D/"latency.json.gz"),"strict":strict,"timings":len(times),"cost_fields":["fallback","blob_bytes","recomputed_windows","sqlite_calls","bounds_rows"]})
if __name__=="__main__":main()
