"""SQLite storage, projection, and degree queries for first-co-visible group pairs."""
from common import *
from time import perf_counter_ns
from pathlib import Path
import sqlite3,statistics,tempfile,shutil,random,platform
EDGE="CREATE TABLE feeds(h INTEGER, src INTEGER, dst INTEGER, first INTEGER NOT NULL, PRIMARY KEY(h,src,dst)) WITHOUT ROWID"
MEM="CREATE TABLE member(h INTEGER, grp INTEGER, unit INTEGER, PRIMARY KEY(h,grp,unit)) WITHOUT ROWID"
FLAT="SELECT src,dst FROM feeds WHERE h=:h AND first<=:t ORDER BY src,dst"
JOIN="""SELECT a.unit,b.unit FROM feeds f JOIN member a ON a.h=f.h AND a.grp=f.src JOIN member b ON b.h=f.h AND b.grp=f.dst WHERE f.h=:h AND f.first<=:t ORDER BY a.unit,b.unit"""
FLATD="""WITH active(src,dst) AS MATERIALIZED (SELECT src,dst FROM feeds WHERE h=:h AND first<=:t),
degrees(u,go,gi) AS (SELECT src,COUNT(*),0 FROM active GROUP BY src UNION ALL SELECT dst,0,COUNT(*) FROM active GROUP BY dst)
SELECT u,SUM(go),SUM(gi) FROM degrees GROUP BY u ORDER BY u"""
JOIND="""WITH counts(g,n) AS MATERIALIZED (SELECT grp,COUNT(*) FROM member WHERE h=:h GROUP BY grp),
active(src,dst) AS MATERIALIZED (SELECT src,dst FROM feeds WHERE h=:h AND first<=:t),
degrees(g,go,gi) AS (SELECT f.src,SUM(c.n),0 FROM active f JOIN counts c ON c.g=f.dst GROUP BY f.src UNION ALL SELECT f.dst,0,SUM(c.n) FROM active f JOIN counts c ON c.g=f.src GROUP BY f.dst),
summed AS (SELECT g,SUM(go) AS go,SUM(gi) AS gi FROM degrees GROUP BY g)
SELECT m.unit,s.go,s.gi FROM summed s JOIN member m ON m.h=:h AND m.grp=s.g ORDER BY m.unit"""
MODES=("flat","flat_shared","grouped")
QUERIES={m:{"pairs":JOIN if m=="grouped" else FLAT,"degrees":JOIND if m=="grouped" else FLATD} for m in MODES}
def build(path,rows,mode):
    tick=perf_counter_ns();db=sqlite3.connect(path);db.execute("PRAGMA page_size=4096");assert db.execute("PRAGMA journal_mode=DELETE").fetchone()==("delete",);db.execute("PRAGMA synchronous=FULL");db.execute("PRAGMA temp_store=MEMORY");db.execute("BEGIN IMMEDIATE");db.execute(EDGE)
    if mode!="flat":db.execute(MEM)
    count=[]
    for hid,z in rows.items():
        groups=dict(z["groups"]);h=int(hid)
        if mode!="flat":db.executemany("INSERT INTO member VALUES(?,?,?)",((h,g,u) for g,us in groups.items() for u in us))
        if mode=="grouped":data=((h,a,b,v) for a,b,v in z["first"])
        else:data=((h,x,y,v) for a,b,v in z["first"] for x in groups[a] for y in groups[b])
        db.executemany("INSERT INTO feeds VALUES(?,?,?,?)",data)
    db.commit();db.close();return (perf_counter_ns()-tick)/1e6
def reader(path):
    db=sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True)
    db.execute("PRAGMA cache_size=-8192");db.execute("PRAGMA temp_store=MEMORY");return db
def constraints(db,mode,rows):
    n=0
    for hid,z in rows.items():
        for check in z["checks"]:
            for k,sql in QUERIES[mode].items():
                records=db.execute(sql,{"h":int(hid),"t":check["at"]}).fetchall()
                assert hashobj(records)==check[k] and (k!="pairs" or len(records)==check["count"]),(hid,k,mode)
            n+=1
    return n
def summarize(samples,cases):
    import numpy as np
    klist=sorted(cases); cubes={}
    for m in MODES:
        for k in ("pairs","degrees"):
            val=np.array([statistics.median(samples[h,c,m,k])/1000 for h,c in klist]);cubes[m,k]=val
    stat={};paired={};labs=np.array([h for h,c in klist]);uniq=np.unique(labs)
    for (m,k),v in cubes.items():stat[m+"_"+k]={"p50_us":float(np.median(v)),"p95_us":float(np.quantile(v,.95)),"mean_us":float(v.mean())}
    for control in ("flat","flat_shared"):
        for k in ("pairs","degrees"):
            a=cubes["grouped",k].reshape(128,4).mean(axis=1);b=cubes[control,k].reshape(128,4).mean(axis=1);rng=np.random.default_rng(364036);idx=rng.integers(0,128,(10000,128));r=a[idx].mean(axis=1)/b[idx].mean(axis=1)
            paired[control+"_"+k]={"ratio_grouped_over_control_mean":float(a.mean()/b.mean()),"ci":np.quantile(r,[.025,.975]).tolist()}
    return {"absolute":stat,"paired":paired}
def main():
    ex=load(D/"extraction.json");assert sha(D/"input.json.gz")==ex["input"]
    inp=load(D/"input.json.gz");rows={h:z for h,z in sorted(inp.items(),key=lambda x:int(x[0])) if int(h)<128};assert len(rows)==128
    layout=list(enumerate(sorted((r,m) for r in range(5) for m in MODES)));schedule=sorted([x for i,x in layout],key=lambda x:hashobj(["build",*x]))
    source={"protocol":sha(D/"PROTOCOL_RU.md"),"input":sha(D/"input.json.gz"),"code":sha(D/"sqlbench.py"),"schedule":schedule,"page_size":4096,"cache_kib":8192,"warm_rounds":9};save(D/"sql-plan.json",source)
    times={m:[] for m in MODES};sizes={};dbs={};meta={};last={};reps=[]
    with tempfile.TemporaryDirectory(dir=D) as tmp:
        for r,m in schedule:
            p=Path(tmp)/(m+str(r)+".sqlite3");t=build(p,rows,m);times[m].append(t);last[m]=p;reps.append([r,m,t,p.stat().st_size])
            if m in sizes:assert sizes[m]==p.stat().st_size
            sizes[m]=p.stat().st_size
        for m in MODES:
            final=D/(m+".sqlite3");shutil.copyfile(last[m],final);db=reader(final);dbs[m]=db;assert db.execute("PRAGMA integrity_check").fetchone()==("ok",);assert constraints(db,m,rows)==512
            objs=db.execute("SELECT name,count(*),sum(pgsize),sum(payload) FROM dbstat GROUP BY name").fetchall()
            meta[m]={"size":sizes[m],"tables":objs,"feeds":db.execute("SELECT count(*) FROM feeds").fetchone()[0],"members":db.execute("SELECT count(*) FROM member").fetchone()[0] if m!="flat" else 0}
        cases={(int(h),c["cut"]):c["at"] for h,z in rows.items() for c in z["checks"]};tasks=[(h,c,m,k) for h,c in cases for m in MODES for k in ("pairs","degrees")];samples={task:[] for task in tasks}
        for rnd in range(-1,9):
            schedule=list(tasks);random.Random(36000+rnd).shuffle(schedule)
            for task in schedule:
                h,c,m,k=task;params={"h":h,"t":cases[h,c]};sql=QUERIES[m][k];db=dbs[m]
                st=perf_counter_ns();data=db.execute(sql,params).fetchall();elapsed=perf_counter_ns()-st
                if rnd>=0:samples[task].append(elapsed)
        for db in dbs.values():db.close()
        extra={h:z for h,z in inp.items() if int(h)>=128}
        if extra:
            ep=Path(tmp)/"native.sqlite3";build(ep,extra,"grouped");db=reader(ep);supp=constraints(db,"grouped",extra);db.close()
        else:supp=0
    raw=[[h,c,m,k,v] for (h,c,m,k),v in sorted(samples.items())];save(D/"timings.json.gz",{"reads_ns":raw,"builds_ms":reps})
    result={"environment":{"python":platform.python_version(),"sqlite":sqlite3.sqlite_version,"os":platform.platform()},"rows":meta,"build_ms":{m:{"median":statistics.median(z),"min":min(z),"max":max(z)} for m,z in times.items()},"read":summarize(samples,cases),"primary_histories":128,"primary_cuts":512,"schema_cut_checks":1536,"extra_cut_checks":supp,"timed_calls":len(tasks)*9,"input_sha":ex["input"],"boundaries":{f:sum(r[f] for r in rows.values()) for f in ("at_boundary","before_boundary")}}
    save(D/"results.json",result);print(json.dumps(result,ensure_ascii=True),flush=True)
if __name__=="__main__":main()
