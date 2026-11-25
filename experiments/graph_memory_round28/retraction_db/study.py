"""Measure independent on-disk SQLite layouts for a fixed-input citation exclusion."""
from collections import defaultdict
import argparse
import os
import platform
import random
import sqlite3
import statistics as st
import struct
from time import perf_counter_ns as clock
from pathlib import Path
import numpy as np
from design import HERE, UP, PRIVATE, key, read, save, sha

FIELDS="score,ord,lo,hi"
CREATE_FULL="(q INTEGER,score REAL,ord INTEGER,lo INTEGER,hi INTEGER, PRIMARY KEY(q,score DESC,ord)) WITHOUT ROWID"
CREATE_SKY="(q INTEGER,bound INTEGER,score REAL,ord INTEGER,lo INTEGER,hi INTEGER, PRIMARY KEY(q,bound)) WITHOUT ROWID"
FULL=f"SELECT {FIELDS} FROM main.r WHERE q=? AND (hi<=? OR lo>=?) ORDER BY score DESC,ord LIMIT 1"
TOP={k:FULL.replace("main.r",f"top{k}.r") for k in (8,64)}
SKY=f"""SELECT * FROM (
 SELECT * FROM (SELECT {FIELDS} FROM sky.pre WHERE q=? AND bound<=? ORDER BY bound DESC LIMIT 1)
 UNION ALL
 SELECT * FROM (SELECT {FIELDS} FROM sky.suf WHERE q=? AND bound>=? ORDER BY bound ASC LIMIT 1)
) ORDER BY score DESC,ord LIMIT 1"""
NAMES=("full","sky","top8","top64")

def prepared():
    plan=read(HERE/"plan.json")
    assert plan["protocol"]==sha(HERE/"PROTOCOL_RU.md") and plan["capture"]==sha(UP/"capture-plan.json")
    assert plan["upstream_queries"]==sha(UP/"evaluate_views.py")
    cap=read(UP/"forecast-seal.json")
    assert cap["plan"]==plan["capture"] and cap["forecasts"]==sha(UP/"state-forecasts.json.gz")
    capture=read(UP/"state-forecasts.json.gz")
    folder=PRIVATE / sha(HERE/"plan.json")
    views=Path("D:/CodexResearch/x20-r28-revoked-spans") / cap["plan"]
    return plan,capture,views,folder

def ranked(arrays, windows):
    chunks=[]
    for w in range(len(windows)):
        prefix="base_"+str(w)+"_"
        a,b,seg,lo,hi=(arrays[prefix+k] for k in ("a","b","seg","lo","hi"))
        assert a.dtype==b.dtype==np.float32 and len(a)<=384
        for delta in range(min(30,len(a))):
            n=len(a)-delta
            start=np.flatnonzero((seg[:n]>=0)&(seg[:n]==seg[delta:]))
            end=start+delta
            scores=a[start]+b[end]
            chunks.extend(zip(scores.tolist(),((w*384+start)*30+delta).tolist(),lo[start].tolist(),hi[end].tolist()))
    assert chunks and all(l<h and np.isfinite(s) for s,o,l,h in chunks)
    chunks.sort(key=lambda x:(-x[0],x[1]))
    return chunks

def scenarios(q,case):
    parts=case["states"]["base"]["parts"]
    others=[x for x in parts if x[:2]!=case["cut"]]
    r=min(others or parts,key=lambda v:key(q+str(v)))
    l,h=case["old_answer"]
    width=min(h-l,r[1]-r[0]);room=r[1]-r[0]-width
    lo=r[0]+int.from_bytes(key("random/"+q)[:8],"big")%(room+1)
    regular={"winner":[l,h],"record":case["cut"],"random":[lo,lo+width]}
    for ix,(a,b,_) in enumerate(parts):
        regular["shown"+str(ix)]=[a,b]
    lower=min(v[0] for v in parts);upper=max(v[1] for v in parts)
    regular["all"]=[lower,upper];regular["outside"]=[upper+1,upper+2]
    return regular

def envelope(rows, side):
    # Descending total score ranks make setdefault retain exactly the winner per endpoint.
    coordinate=3 if side=="pre" else 2
    by={}
    for ix,r in enumerate(rows):
        by.setdefault(r[coordinate],ix)
    best=len(rows);result=[]
    for boundary in sorted(by,reverse=(side=="suf")):
        if by[boundary]<best:
            best=by[boundary];result.append((boundary,*rows[best]))
    return result

def connect(folder,create):
    db=sqlite3.connect(folder/"full.sqlite")
    for name in NAMES[1:]:
        db.execute(f"ATTACH DATABASE ? AS {name}",(str(folder/(name+".sqlite")),))
    if create:
        for name in ("main",*NAMES[1:]):
            db.execute(f"PRAGMA {name}.journal_mode=DELETE")
            db.execute(f"PRAGMA {name}.synchronous=FULL")
        for name in ("main","top8","top64"):
            db.execute(f"CREATE TABLE {name}.r "+CREATE_FULL)
        for t in ("pre","suf"):
            db.execute(f"CREATE TABLE sky.{t} "+CREATE_SKY)
    return db

def build():
    plan,cases,views,folder=prepared()
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/"complete.json").exists():
        print("already built", folder, flush=True);return
    if (folder/"full.sqlite").exists():
        raise FileExistsError("Incomplete attempt; use a new isolated directory after diagnosing the log")
    db=connect(folder,True);info={};refs={}
    for ix,q in enumerate(plan["qids"]):
        case=cases[q];src=views/(q+".npz")
        assert sha(src)==case["arrays"]
        tic=clock()
        with np.load(src,allow_pickle=False) as ar:
            rows=ranked(ar,case["states"]["base"]["windows"])
        times={"enumerate_sort_ns":clock()-tic}
        def write(name,table,values):
            tic=clock()
            db.executemany("INSERT INTO "+table+" VALUES ("+",".join("?" for _ in range(len(values[0])+1))+")",((ix,*r) for r in values))
            db.commit();times[name]=clock()-tic
        write("full_write_ns","main.r",rows)
        for k in (8,64):
            write(f"top{k}_write_ns",f"top{k}.r",rows[:k])
        sizes={}
        for side in ("pre","suf"):
            tic=clock();records=envelope(rows,side)
            times[side+"_construct_ns"]=clock()-tic;sizes[side]=len(records)
            write(side+"_write_ns","sky."+side,records)
        queries={}
        for name,(l,h) in scenarios(q,case).items():
            assert l<h
            found=next(((i+1,v) for i,v in enumerate(rows) if v[3]<=l or v[2]>=h),(None,None))
            queries[name]={"ban":[l,h],"rank":found[0],"answer":found[1]}
        assert queries["all"]["rank"] is None and queries["outside"]["rank"]==1
        for k in (8,64):
            sizes["top"+str(k)]=min(k,len(rows))
        info[q]={"article":case["title"],"n":len(rows),"front":sizes,"build":times}
        refs[q]=queries
        if (ix+1)%16==0:print("indexed",ix+1,flush=True)
    db.close()
    save(HERE/"reference.json.gz",refs);save(HERE/"build-rows.json.gz",info)
    complete={"plan":sha(HERE/"plan.json"),"code":sha(Path(__file__)),"input":sha(UP/"forecast-seal.json"),
              "databases":{k:{"bytes":(folder/(k+".sqlite")).stat().st_size,"sha256":sha(folder/(k+".sqlite"))} for k in NAMES},
              "rows":sha(HERE/"build-rows.json.gz"),"reference":sha(HERE/"reference.json.gz"),"sqlite":sqlite3.sqlite_version}
    save(folder/"complete.json",complete);save(HERE/"build-seal.json",complete)

def pack(row):
    return bytes([0]) if row is None else struct.pack("<BfIii",1,*row)

def query(db,name,ix,l,h):
    if name=="sky":
        return db.execute(SKY,(ix,l,ix,h)).fetchone(),1,0
    if name=="full":
        return db.execute(FULL,(ix,l,h)).fetchone(),1,0
    k=int(name[3:]);first=db.execute(TOP[k],(ix,l,h)).fetchone()
    if first is not None:
        return first,1,0
    return db.execute(FULL,(ix,l,h)).fetchone(),2,1

def measure():
    plan,cases,views,folder=prepared();built=read(HERE/"build-seal.json");info=read(HERE/"build-rows.json.gz")
    assert read(folder/"complete.json")==built and built["reference"]==sha(HERE/"reference.json.gz")
    db=connect(folder,False);db.execute("PRAGMA query_only=1")
    for schema in ("main","sky","top8","top64"):
        db.execute(f"PRAGMA {schema}.cache_size=-32768")
    oracle=read(HERE/"reference.json.gz");validations=0;reg=defaultdict(lambda:defaultdict(list))
    timed=[];rng=random.Random(28196);detail={}
    for ix,q in enumerate(plan["qids"]):
        for case,r in oracle[q].items():
            l,h=r["ban"];a=r["answer"]
            for m in NAMES:
                row,rounds,extra=query(db,m,ix,l,h)
                assert pack(row)==pack(a),(ix,q,case,m,row,a)
                validations+=1
                if case in ("winner","record","random"):
                    reg[m][case].append({"calls":rounds,"transfer":len(pack(row))+extra, "app_bytes":len(pack(row)),
                                        "fallback":extra,"q":q,"rank_visited":r["rank"] or info[q]["n"]})
            if q in plan["panel"] and case in ("winner","record","random"):
                timed.append((q,ix,case,l,h))
    # Complete DB page cache preparation for this item set under the same per-schema limit.
    for _,ix,_,l,h in timed:
        for m in NAMES:query(db,m,ix,l,h)
    samples=[]
    for rep in range(24):
        sequence=timed.copy();rng.shuffle(sequence)
        for q,ix,case,l,h in sequence:
            arms=list(NAMES);rng.shuffle(arms)
            for m in arms:
                tic=clock();row,calls,extra=query(db,m,ix,l,h);payload=pack(row);ns=clock()-tic
                samples.append([rep,q,case,m,ns])
    plans={m:[r[-1] for r in db.execute("EXPLAIN QUERY PLAN "+s, (0,0,0,1) if m=="sky" else (0,0,1))]
           for m,s in {"full":FULL,"sky":SKY,"top8":TOP[8],"top64":TOP[64]}.items()}
    db.close()
    save(HERE/"measurements.json.gz",{"samples":samples,"regular":reg,"validations":validations,"plans":plans})
    save(HERE/"measurement-seal.json",{"build":sha(HERE/"build-seal.json"),"data":sha(HERE/"measurements.json.gz"),
         "code":sha(Path(__file__)),"runtime":platform.python_version(),"processor":platform.processor(),"sqlite":sqlite3.sqlite_version,
          "panel_questions":len(plan["panel"]),"tasks":len(timed),"reps":24,"samples":len(samples),"validations":validations})

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("build","measure"))
    args=p.parse_args()
    if args.stage=="build":build()
    else:measure()
