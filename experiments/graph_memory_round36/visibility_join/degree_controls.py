from operators import *
DELTA="CREATE TABLE change(h INTEGER, u INTEGER, t INTEGER, go INTEGER NOT NULL, gi INTEGER NOT NULL, PRIMARY KEY(h,u,t)) WITHOUT ROWID"
DREAD="SELECT u,SUM(go),SUM(gi) FROM change WHERE h=:h AND t<=:t GROUP BY u ORDER BY u"
FOLD="""WITH active(s,d) AS MATERIALIZED (SELECT src,dst FROM feeds WHERE h=:h AND first<=:t),
endpoints(u,go,gi) AS (SELECT s,1,0 FROM active UNION ALL SELECT d,0,1 FROM active)
SELECT u,SUM(go),SUM(gi) FROM endpoints GROUP BY u ORDER BY u"""
def create(path,rows,full):
    st=perf_counter_ns();db=sqlite3.connect(path);db.execute("PRAGMA page_size=4096");assert db.execute("PRAGMA journal_mode=DELETE").fetchone()==("delete",);db.execute("PRAGMA synchronous=FULL");db.execute("PRAGMA temp_store=MEMORY");db.execute("BEGIN IMMEDIATE");db.execute(DELTA)
    if full:db.execute(EDGE)
    for h,z in rows.items():
        gs=dict(z["groups"]);h=int(h);d={};pairs=[]
        for a,b,t in z["first"]:
            for x in gs[a]:
                for y in gs[b]:
                    d.setdefault((x,t),[0,0])[0]+=1;d.setdefault((y,t),[0,0])[1]+=1
                    if full:pairs.append((h,x,y,t))
        db.executemany("INSERT INTO change VALUES(?,?,?,?,?)",((h,u,t,go,gi) for (u,t),(go,gi) in d.items()))
        if full:db.executemany("INSERT INTO feeds VALUES(?,?,?,?)",pairs)
    db.commit();db.close();return (perf_counter_ns()-st)/1e6
def main():
    inp=load(D/"input.json.gz");rows={h:z for h,z in sorted(inp.items(),key=lambda x:int(x[0])) if int(h)<128};cases={(int(h),c["cut"]):c for h,z in rows.items() for c in z["checks"]}
    save(D/"degree-plan.json",{"stage1":sha(D/"results.json"),"stage2":sha(D/"operator-results.json"),"protocol":sha(D/"DEGREE_CONTROL_RU.md"),"script":sha(D/"degree_controls.py")})
    specs={"flat":("flat",FLATD),"flat_fold":("flat",FOLD),"grouped_arity":("grouped_arity",COSTD),"flat_delta":("flat_delta",DREAD),"delta_only":("delta_only",DREAD)};dur={};sz={}
    with tempfile.TemporaryDirectory(dir=D) as tmp:
        tmp=Path(tmp);schedule=sorted([(m,r) for m in ("flat_delta","delta_only") for r in range(5)],key=lambda x:hashobj(["delta",*x]))
        for m,r in schedule:
            p=tmp/(m+str(r)+".sqlite3");dur.setdefault(m,[]).append(create(p,rows,m=="flat_delta"));shutil.copyfile(p,D/(m+".sqlite3"))
        con={}
        for m,(p,sql) in specs.items():
            path=D/(p+".sqlite3");con[m]=reader(path);sz[m]=path.stat().st_size
            for (h,c),item in cases.items():
                params={"h":h,"t":item["at"]};assert hashobj(con[m].execute(sql,params).fetchall())==item["degrees"]
                if m=="flat_delta":assert hashobj(con[m].execute(FLAT,params).fetchall())==item["pairs"]
        tasks=[(h,c,m) for h,c in cases for m in specs];tim={t:[] for t in tasks}
        for r in range(-1,9):
            order=list(tasks);random.Random(36700+r).shuffle(order)
            for t in order:
                h,c,m=t;pr={"h":h,"t":cases[h,c]["at"]};db=con[m];sql=specs[m][1];st=perf_counter_ns();v=db.execute(sql,pr).fetchall();dt=perf_counter_ns()-st
                if r>=0:tim[t].append(dt)
        for db in con.values():db.close()
    ids=sorted(cases);v={m:np.array([statistics.median(tim[h,c,m])/1000 for h,c in ids]) for m in specs};ix=np.random.default_rng(36836).integers(0,128,(10000,128));stats={}
    for m,a in v.items():
        b=v["flat"];ag=a.reshape(128,4).mean(axis=1);bg=b.reshape(128,4).mean(axis=1);ratio=ag[ix].mean(axis=1)/bg[ix].mean(axis=1)
        stats[m]={"p50_us":float(np.median(a)),"p95_us":float(np.quantile(a,.95)),"mean_us":float(a.mean()),"ratio_to_flat":float(a.mean()/b.mean()),"ci":np.quantile(ratio,[.025,.975]).tolist()}
    save(D/"degree-timings.json.gz",{"builds_ms":dur,"reads_ns":[[h,c,m,x] for (h,c,m),x in sorted(tim.items())]});save(D/"degree-results.json",{"methods":stats,"sizes":sz,"median_build_ms":{m:statistics.median(a) for m,a in dur.items()},"read_calls":9*len(tasks),"plan":sha(D/"degree-plan.json")});print(stats,sz)
if __name__=="__main__":main()
