"""Build independent SQLite rank and 2-D max layouts with stable span dominance."""
from time import perf_counter_ns as now
from pathlib import Path
import sqlite3
import numpy as np
from multiban_design import D,PRIVATE,source,arrays,read,save,sha

SCHEMA="(q INTEGER,score REAL,ord INTEGER,lo INTEGER,hi INTEGER,PRIMARY KEY(q,score DESC,ord)) WITHOUT ROWID"
def state():
    p,cases,old,logs=source();plan=read(D/"plan.json");fixture=read(D/"scenario-seal.json")
    assert fixture["input"]==sha(D/"plan.json") and fixture["scenarios"]==sha(D/"scenarios.json.gz")
    base=PRIVATE/sha(D/"plan.json");base.mkdir(exist_ok=True)
    return p,cases,old,logs,base

def structure(lo,hi):
    n=len(lo);coords,compressed=np.unique(hi,return_inverse=True);m=len(coords)
    order=np.lexsort((np.arange(n),hi,-lo))
    prefix=[n]*(m+1);survivors=[];cells=[[] for _ in range(m+1)]
    low=lo.tolist();ei=(compressed+1).tolist()
    for rank in order.tolist():
        j=ei[rank];z=j;best=n
        while z and best>rank:
            best=min(best,prefix[z]);z-=z&-z
        if best<=rank:continue
        survivors.append(rank);start=low[rank]
        while j<=m:
            if rank<prefix[j]:
                prefix[j]=rank
                if cells[j] and cells[j][-1][0]==start:cells[j][-1]=(start,rank)
                else:cells[j].append((start,rank))
            j+=j&-j
    return sorted(survivors),coords,cells

def open_all(old,logs,base):
    db=sqlite3.connect(old/"full.sqlite")
    for name,path in (("pareto",base/"pareto.sqlite"),("rng",base/"range.sqlite"),("top64",old/"top64.sqlite"),("bounds",logs/"bounds.sqlite"),("zip",logs/"zip.sqlite")):
        db.execute(f"ATTACH DATABASE ? AS {name}",(str(path),))
    for name in ("main","pareto","rng","top64","bounds","zip"):db.execute("PRAGMA "+name+".cache_size=-32768")
    return db

def build():
    p,cases,old,logs,base=state()
    if (D/"build-seal.json").exists():return
    if (base/"pareto.sqlite").exists():raise FileExistsError("Incomplete attempt before new build")
    db=open_all(old,logs,base)
    db.execute("CREATE TABLE pareto.r "+SCHEMA)
    db.execute("CREATE TABLE rng.coord(q INTEGER,endpoint INTEGER,i INTEGER,PRIMARY KEY(q,endpoint)) WITHOUT ROWID")
    db.execute("CREATE TABLE rng.cell(q INTEGER,bucket INTEGER,threshold INTEGER,score REAL,ord INTEGER,lo INTEGER,hi INTEGER,PRIMARY KEY(q,bucket,threshold)) WITHOUT ROWID")
    rows={}
    for ix,q in enumerate(p["qids"]):
        t=now();score,o,lo,hi=arrays(db,ix);load_ns=now()-t
        t=now();s,coords,cells=structure(lo,hi);processing=now()-t
        def candidate(i):return float(score[i]),int(o[i]),int(lo[i]),int(hi[i])
        t=now();db.executemany("INSERT INTO pareto.r VALUES (?,?,?,?,?)",((ix,*candidate(i)) for i in s))
        db.commit();store_p=now()-t;t=now()
        db.executemany("INSERT INTO rng.coord VALUES (?,?,?)",((ix,int(e),j) for j,e in enumerate(coords,1)))
        db.executemany("INSERT INTO rng.cell VALUES (?,?,?,?,?,?,?)",((ix,j,threshold,*candidate(i)) for j,changes in enumerate(cells) for threshold,i in changes))
        db.commit();store_r=now()-t
        rows[q]={"all":len(o),"pareto":len(s),"ends":len(coords),"cell_winners":sum(map(len,cells)),
            "load_ns":load_ns,"construct_ns":processing,"pareto_write_ns":store_p,"range_write_ns":store_r}
        if (ix+1)%16==0:print("built",ix+1,flush=True)
    db.close();save(D/"build-rows.json.gz",rows)
    save(D/"build-seal.json",{"protocol":sha(D/"plan.json"),"fixture":sha(D/"scenario-seal.json"),"code":sha(Path(__file__)),
        "data":sha(D/"build-rows.json.gz"),"files":{n:{"sha":sha(base/(n+".sqlite")),"bytes":(base/(n+".sqlite")).stat().st_size} for n in ("pareto","range")}})
if __name__=="__main__":build()
