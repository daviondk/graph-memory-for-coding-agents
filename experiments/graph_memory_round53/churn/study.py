"""Fixed trace replay, independent cross-check, timings, paired intervals, SQLite size and plans."""
from collections import defaultdict
from pathlib import Path
from time import perf_counter_ns as clock
import platform
import random
import sqlite3
import tempfile
import numpy as np
from engine import Engine,connect,CURRENT,PREV,VER,RAW
from source import HERE,WORK,read,save,sha,reads

PLANS=["interval","candidate","journal"]
def expected(events,t):
    r=events[t-1]["winner"] if t else None
    return tuple(r) if r is not None else None
def check_state(db):
    assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
    overlap=db.execute("""SELECT count(*) FROM edge x JOIN edge y ON x.q=y.q AND x.src=y.src AND x.dst=y.dst AND x.beg<y.beg
      AND (x.end IS NULL OR x.end>y.beg)""").fetchone()[0]
    assert overlap==0
def execute(path,work,plan,m,verify=False):
    db=connect(path);eng=Engine(db,plan,create=True);t_write=t_read=0
    rec=[]
    for q,ev in work.items():
        for row in ev:
            t=row["t"];ask=reads(m,q,t)
            tick=clock();actual=eng.update(q,t,row["born"],row["delta"],row["sha"]);t_write+=clock()-tick
            assert actual
            tick=clock()
            got=[eng.get(q,v) for v in ask]
            t_read+=clock()-tick
            assert got==[expected(ev,v) for v in ask]
            if verify:
                assert eng.get(q,t)==expected(ev,t)
        if verify:
            for u in range(len(ev)+1):assert eng.get(q,u)==expected(ev,u)
    tick=clock();db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone();cp=clock()-tick
    table_counts={n:db.execute("SELECT count(*) FROM "+n).fetchone()[0] for n in ("source","edge","receipt","winner")+(("cv",) if plan=="candidate" else ())}
    sql,args={"interval":(RAW,(1,1,"q01",1)),"candidate":(VER,("q01",1,1)),"journal":(PREV,("q01",1))}[plan]
    profile=[x[-1] for x in db.execute("EXPLAIN QUERY PLAN "+sql,args)]
    if verify:check_state(db)
    db.close()
    return {"write_ms":t_write/1.e6,"read_ms":t_read/1.e6,"checkpoint_ms":cp/1.e6,
            "total_ms":(t_write+t_read+cp)/1.e6,"bytes":path.stat().st_size,"rows":table_counts,"query_plan":profile}
def integrity(work):
    with tempfile.TemporaryDirectory(dir=WORK) as temp:
        results={p:execute(Path(temp)/(p+".sqlite"),work,p,8,True) for p in PLANS}
    return results
def main():
    WORK.mkdir(exist_ok=True);reg=read(HERE/"registration.json")
    assert reg["work_sha"]==sha((HERE/"workload.json.gz").read_bytes()) and reg["protocol_sha"]==sha((HERE/"PROTOCOL_RU.md").read_bytes())
    work=read(HERE/"workload.json.gz");check=integrity(work)
    rng=random.Random(530271);runs=[]
    with tempfile.TemporaryDirectory(dir=WORK) as temp:
        for rep in range(6):
            modes=[0,1,8];rng.shuffle(modes)
            for m in modes:
                plans=list(PLANS);rng.shuffle(plans)
                for ordinal,p in enumerate(plans):
                    path=Path(temp)/f"{rep}-{m}-{p}.sqlite"
                    row=execute(path,work,p,m)
                    runs.append({"repetition":rep,"reads_per_frame":m,"plan":p,"position":ordinal,**row})
                    path.unlink()
    save("timings.json.gz",runs)
    means={};intervals={}
    for m in (0,1,8):
        means[m]={}
        for p in PLANS:
            subset=[r for r in runs if r["plan"]==p and r["reads_per_frame"]==m]
            means[m][p]={k:float(np.mean([r[k] for r in subset])) for k in ("write_ms","read_ms","checkpoint_ms","total_ms","bytes")}
        intervals[m]={}
        for c in ("candidate","interval"):
            matrix=[]
            for i in range(6):
                z={r["plan"]:r["total_ms"] for r in runs if r["reads_per_frame"]==m and r["repetition"]==i}
                matrix.append([z[c],z["journal"]])
            a=np.array(matrix);draws=np.random.default_rng(530271).integers(6,size=(10000,6))
            vals=a[draws].mean(1);ratios=vals[:,0]/vals[:,1]
            intervals[m][c+"_over_journal"]={"speed_ratio":float(a[:,0].mean()/a[:,1].mean()),"ci95":np.quantile(ratios,[.025,.975]).tolist(),
                                               "wins":int((a[:,0]>a[:,1]).sum())}
    save("results.json",{"means":means,"paired":intervals,"correctness":{p:{k:z[k] for k in ("rows","bytes","query_plan")} for p,z in check.items()},
         "n_versions_verified_including_empty":sum(1+len(r) for r in work.values()),"repetitions":6,
         "interactive_requests_in_primary":8*sum(map(len,work.values())),"sqlite":sqlite3.sqlite_version,"python":platform.python_version(),
         "platform":platform.platform(),"num_traces":len(work)})
    print(means);print(intervals)
if __name__=="__main__":main()

