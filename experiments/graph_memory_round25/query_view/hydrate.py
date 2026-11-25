"""Measure SQLite layout hydration and source reads in one lookup."""
from collections import Counter,defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import hashlib
import random
import sqlite3
import numpy as np
from evaluate import METHODS
from make_fixture import D,DB,PRIVATE,decode,pack,read,write,sha
from ranking import bag,select
FILE=PRIVATE/"compressed-views.sqlite"

def build(source):
    with TemporaryDirectory(dir=PRIVATE) as tmp:
        stage=Path(tmp)/"views.sqlite";db=sqlite3.connect(stage)
        db.execute("create table data(sid text,method text,data blob,primary key(sid,method)) without rowid")
        for sid,vblob,iblob,cost_blob in source.execute("select sid,projected,inverted,costs from snapshot order by sid"):
            v=decode(vblob);rows=v["rows"];coords=[r["coords"] for r in rows];lens=[r["length"] for r in rows]
            known=[r["known"] for r in rows];bounds=[r["unknown_max"] for r in rows];masks=[r["bits"].to_bytes(32,"little").hex() for r in rows]
            common=[coords,lens,v["df"]];projected=[*common,v["first"],known,bounds]
            inv={w:sorted(([int(i),n] for i,n in entries.items())) for w,entries in decode(iblob).items()}
            rep={"scan":coords,"df_scan":common,"exact_lazy":projected,"projected":projected,
                 "bloom_scan":[*projected,masks],"bloom_lazy":[*projected,masks],
                 "bloom_cold":[*common,[r["max"] for r in rows],masks],"inverted":[coords,lens,inv]}
            costs=decode(cost_blob)
            for m,data in sorted(rep.items()):
                b=pack(data);assert len(b)==costs[m],(m,len(b),costs[m])
                db.execute("insert into data values(?,?,?)",(sid,m,b))
        db.commit();db.execute("vacuum");db.close()
        if FILE.exists():assert sha(stage)==sha(FILE)
        else:stage.replace(FILE)

def interpret(data,m):
    coords=data if m=="scan" else data[0]
    rows=[{"coords":x} for x in coords];view={"rows":rows}
    if m=="scan":return view,None
    for row,n in zip(rows,data[1]):row["length"]=n
    if m=="inverted":
        return view,{w:dict(items) for w,items in data[2].items()}
    view["df"]=data[2]
    if m=="df_scan":return view,None
    if m=="bloom_cold":
        for row,z,b in zip(rows,data[3],data[4]):
            row["max"]=z;row["bits"]=int.from_bytes(bytes.fromhex(b),"little")
        return view,None
    view["first"]=data[3]
    for i,r in enumerate(rows):
        r["known"]=data[4][i];r["unknown_max"]=data[5][i]
        if m.startswith("bloom"):r["bits"]=int.from_bytes(bytes.fromhex(data[6][i]),"little")
    return view,None

def main():
    source=sqlite3.connect(DB.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    build(source)
    meta=sqlite3.connect(FILE.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    ref={(r["g"],r["q"]):r for r in read(D/"decisions.json.gz")}
    out=[]
    for sid,q,query in source.execute("select sid,q,question from future order by sid,q"):
        age=ref[sid,q];rng=random.Random(hashlib.sha256(("load/"+q).encode()).digest())
        reps=4 if int.from_bytes(hashlib.sha256(("load-repeat/"+q).encode()).digest()[:2],"little")%8==0 else 1
        for rep in range(reps):
            choices=list(METHODS);rng.shuffle(choices)
            for m in choices:
                fetched=0;ncalls=0
                def fetch(i):
                    nonlocal fetched,ncalls
                    (raw,)=source.execute("select body from payload where sid=? and idx=?",(sid,i)).fetchone()
                    fetched+=len(raw);ncalls+=1
                    return bag(raw.decode())
                t=perf_counter_ns()
                (blob,)=meta.execute("select data from data where sid=? and method=?",(sid,m)).fetchone()
                v,inv=interpret(decode(blob),m)
                if m=="scan":
                    # The scan itself derives lengths from payloads. The checked field is
                    # populated inside its actual fetch callback, incurring no extra reads.
                    def scan_fetch(i):
                        terms=fetch(i)
                        v["rows"][i]["length"]=sum(terms.values());return terms
                    winner=select(v,query,m,scan_fetch)
                else:winner=select(v,query,m,fetch,inv)
                ns=perf_counter_ns()-t
                assert winner==age["arms"][m][0] and fetched==age["arms"][m][3] and ncalls==age["arms"][m][2] and len(blob)==age["size"][m]
                out.append([age["c"],sid,q,m,rep,ns,len(blob)+fetched])
    source.close();meta.close()
    summary={}
    for corpus in ("isetrace","squad"):
        summary[corpus]={}
        for m in METHODS:
            selected=[r for r in out if r[0]==corpus and r[3]==m and r[4]==0]
            summary[corpus][m]={"n":len(selected),"mean_sql_bytes":np.mean([r[6] for r in selected]),"p50_us":np.median([r[5] for r in selected])/1000,
              "p95_us":np.quantile([r[5] for r in selected],.95)/1000}
    write(D/"hydrate-times.json.gz",out);write(D/"hydrate-results.json",{"summary":summary,"state_sqlite":sha(FILE),"fixture_bytes":FILE.stat().st_size,
         "observations":len(out),"log":sha(D/"hydrate-times.json.gz"),"protocol":sha(D/"COLD_VIEW_RU.md")})
    for co,v in summary.items():print(co,{m:round(s["p50_us"],1) for m,s in v.items()})
if __name__=="__main__":main()
