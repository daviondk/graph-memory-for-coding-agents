"""Diagnostic plans and cached endpoint arities after the registered storage comparison."""
from sqlbench import *
import numpy as np
CROSS=JOIN.replace("JOIN member","CROSS JOIN member")
COSTD="""WITH active(src,dst,ns,nd) AS MATERIALIZED (SELECT src,dst,ns,nd FROM feeds WHERE h=:h AND first<=:t),
degrees(g,go,gi) AS (SELECT src,SUM(nd),0 FROM active GROUP BY src UNION ALL SELECT dst,0,SUM(ns) FROM active GROUP BY dst),
summed AS (SELECT g,SUM(go) AS go,SUM(gi) AS gi FROM degrees GROUP BY g)
SELECT m.unit,s.go,s.gi FROM summed s CROSS JOIN member m ON m.h=:h AND m.grp=s.g ORDER BY m.unit"""
def arity_build(path,rows):
    tick=perf_counter_ns();db=sqlite3.connect(path);db.execute("PRAGMA page_size=4096");assert db.execute("PRAGMA journal_mode=DELETE").fetchone()==("delete",);db.execute("PRAGMA synchronous=FULL");db.execute("PRAGMA temp_store=MEMORY");db.execute("BEGIN IMMEDIATE");db.execute(EDGE.replace("PRIMARY KEY(h,src,dst)","ns INTEGER NOT NULL, nd INTEGER NOT NULL, PRIMARY KEY(h,src,dst)"));db.execute(MEM)
    for h,z in rows.items():
        groups=dict(z["groups"]);h=int(h);db.executemany("INSERT INTO member VALUES(?,?,?)",((h,g,u) for g,us in groups.items() for u in us))
        db.executemany("INSERT INTO feeds VALUES(?,?,?,?,?,?)",((h,a,b,v,len(groups[a]),len(groups[b])) for a,b,v in z["first"]))
    db.commit();db.close();return (perf_counter_ns()-tick)/1e6
def main():
    inp=load(D/"input.json.gz");rows={h:z for h,z in sorted(inp.items(),key=lambda x:int(x[0])) if int(h)<128}
    freeze={"input":sha(D/"input.json.gz"),"earlier_result":sha(D/"results.json"),"protocol":sha(D/"OPERATOR_PROTOCOL_RU.md"),"script":sha(D/"operators.py")};save(D/"operator-plan.json",freeze)
    with tempfile.TemporaryDirectory(dir=D) as tmp:
        tmp=Path(tmp);builds=[];db={};sizes={};plans={}
        for rep in range(5):
            p=tmp/("arity"+str(rep)+".sqlite3");builds.append(arity_build(p,rows))
        shutil.copyfile(p,D/"grouped_arity.sqlite3")
        defs={"flat":("flat",FLAT,FLATD),"group_auto":("grouped",JOIN,JOIND),"group_fixed":("grouped",CROSS,JOIND),"flat_stats":("flat",FLAT,FLATD),"group_stats":("grouped",JOIN,JOIND),"group_arity":("grouped_arity",CROSS,COSTD)}
        for m,(base,pq,dq) in defs.items():
            p=D/(base+".sqlite3")
            if m.endswith("stats"):
                v=tmp/(m+".sqlite3");shutil.copyfile(p,v);w=sqlite3.connect(v);w.execute("ANALYZE");w.commit();w.close();p=v
            sz=p.stat().st_size;sizes[m]=sz;r=reader(p);db[m]=r;plans[m]={k:r.execute("EXPLAIN QUERY PLAN "+s,{"h":0,"t":1}).fetchall() for k,s in [("pairs",pq),("degrees",dq)]}
            for h,rec in rows.items():
                for c in rec["checks"]:
                    for i,k in [(1,"pairs"),(2,"degrees")]:assert hashobj(r.execute(defs[m][i],{"h":int(h),"t":c["at"]}).fetchall())==c[k]
        cases={(int(h),c["cut"]):c["at"] for h,z in rows.items() for c in z["checks"]};tasks=[(h,c,m,k) for h,c in cases for m in defs for k in ("pairs","degrees")];tim={t:[] for t in tasks}
        for rep in range(-1,9):
            sched=list(tasks);random.Random(36500+rep).shuffle(sched)
            for t in sched:
                h,c,m,k=t;sql=defs[m][1 if k=="pairs" else 2];pr={"h":h,"t":cases[h,c]};con=db[m];st=perf_counter_ns();v=con.execute(sql,pr).fetchall();du=perf_counter_ns()-st
                if rep>=0:tim[t].append(du)
        for con in db.values():con.close()
    g={};means={};ids=sorted(cases);rng=np.random.default_rng(364036);draw=rng.integers(0,128,(10000,128))
    for m in defs:
        g[m]={}
        for k in ("pairs","degrees"):
            val=np.array([statistics.median(tim[h,c,m,k])/1000 for h,c in ids]);means[m,k]=val.reshape(128,4).mean(axis=1)
            ref=means.get(("flat",k),means[m,k]);ratio=means[m,k][draw].mean(axis=1)/ref[draw].mean(axis=1);g[m][k]={"p50_us":float(np.median(val)),"p95_us":float(np.quantile(val,.95)),"mean_us":float(val.mean()),"ratio_vs_flat":float(val.mean()/ref.mean()),"ci":np.quantile(ratio,[.025,.975]).tolist()}
    save(D/"operator-timings.json.gz",{"raw":[[h,c,m,k,ns] for (h,c,m,k),ns in sorted(tim.items())],"arity_build_ms":builds})
    save(D/"operator-results.json",{"times":g,"bytes":sizes,"plans":plans,"arity_build_ms":builds,"queries":len(tasks)*9,"distinct_checked":len(tasks),"plan":sha(D/"operator-plan.json")});print({k:[round(n['mean_us'],2) for n in g[k].values()] for k in g},sizes)
if __name__=="__main__":main()
