"""Warm-cache SQLite full scan, lazy streaming, SQL sort and materialized-rank controls."""
from collections import defaultdict
from pathlib import Path
import os
import random
import sqlite3
import statistics
import sys
import time

from operators import np,index,suffix_bounds,read
from measure import HERE,load,put,sha,select,boot_ratio

PRIVATE=Path(os.environ.get("THRESHOLD_DB_HOME","D:/CodexResearch/x20-threshold-read"))
DB=PRIVATE/"numeric-v1.sqlite"
DENSE_SQL="select unit from dense where q=? order by r"
JOIN_SQL="select d.unit,p.cost from dense d join prior p on p.t=? and p.unit=d.unit where d.q=? order by d.g+p.value desc,d.r"
FINAL_SQL="select unit,cost from final where q=? order by k"
COLS_SQL="select value,cost from prior where t=? order by unit"
METHODS=("vector","stream","sql","final")


def fixture():
    rows=[]
    for n,rec in sorted(load(HERE/"inputs.json")["shards"].items()):
        assert sha(HERE/n)==rec["sha"]
        rows.extend(load(HERE/n))
    return sorted(rows,key=lambda x:x["t"])


def build():
    PRIVATE.mkdir(parents=True,exist_ok=True)
    if DB.exists():
        rec=load(HERE/"sqlite-build.json");assert sha(DB)==rec["db_sha"]
        return
    work=PRIVATE/"numeric-building.sqlite"
    if work.exists():work=PRIVATE/f"numeric-building-{time.time_ns()}.sqlite"
    c=sqlite3.connect(work);c.execute("pragma page_size=4096");c.execute("pragma journal_mode=delete")
    c.executescript("""
    create table prior(t integer,unit integer,value real not null,cost integer not null,primary key(t,unit)) without rowid;
    create table query(q integer primary key,t integer not null);
    create table dense(q integer,r integer,unit integer not null,g real not null,primary key(q,r)) without rowid;
    """)
    start=time.perf_counter();q=0
    data=fixture()
    for t,tr in enumerate(data):
        c.executemany("insert into prior values (?,?,?,?)",[(t,j,v,price) for j,(v,price) in enumerate(zip(tr["prior"],tr["costs"],strict=True))])
        for row in sorted(tr["queries"],key=lambda z:z["q"]):
            c.execute("insert into query values (?,?)",(q,t))
            c.executemany("insert into dense values (?,?,?,?)",[(q,r,node,g) for r,(node,g) in enumerate(zip(row["order"],tr["signal"],strict=True))])
            q+=1
    c.commit();base_seconds=time.perf_counter()-start
    page=c.execute("pragma page_size").fetchone()[0];base=c.execute("pragma page_count").fetchone()[0]*page
    start=time.perf_counter()
    c.execute("create table final(q integer,k integer,unit integer not null,cost integer not null,primary key(q,k)) without rowid")
    c.execute("""insert into final
        select d.q,row_number() over (partition by d.q order by d.g+p.value desc,d.r),d.unit,p.cost
        from dense d join query v on v.q=d.q join prior p on p.t=v.t and p.unit=d.unit""")
    c.commit();final_seconds=time.perf_counter()-start
    total=c.execute("pragma page_count").fetchone()[0]*page
    assert c.execute("select count(*) from dense").fetchone()==c.execute("select count(*) from final").fetchone()
    assert c.execute("pragma integrity_check").fetchall()==[("ok",)]
    plans={label:[r[3] for r in c.execute("explain query plan "+sql,args)] for label,sql,args in
           (("rank",DENSE_SQL,(0,)),("sql_sort",JOIN_SQL,(0,0)),("materialized",FINAL_SQL,(0,)),("static",COLS_SQL,(0,)))}
    c.close();work.rename(DB)
    put(HERE/"sqlite-build.json",{"db_sha":sha(DB),"sqlite":sqlite3.sqlite_version,"source":sha(HERE/"inputs.json"),"protocol":sha(HERE/"SQL_PROTOCOL_RU.md"),
         "page_size":page,"base_bytes":base,"final_extra_bytes":total-base,"total_bytes":total,"base_seconds":base_seconds,"final_seconds":final_seconds,
         "query_plans":plans,"q":q,"trajectories":len(data)})


class Stream:
    def __init__(self,cursor,n):
        self.cursor=cursor;self.n=n;self.start=0;self.page=[];self.fetched=0
    def __len__(self):
        return self.n
    def __getitem__(self,i):
        if i>=self.start+len(self.page):
            self.start+=len(self.page)
            self.page=self.cursor.fetchmany(16)
            self.fetched+=len(self.page)
        assert self.start<=i<self.start+len(self.page)
        return self.page[i-self.start][0]


def execute(c,q,t,sign,up,ix,policy,mode):
    if mode=="vector":
        cur=c.execute(DENSE_SQL,(q,));a=cur.fetchall();cur.close();n=len(a)
        order=np.fromiter((r[0] for r in a),dtype=int,count=n)
        output,_=read("vector",order,sign,up,ix,2048,policy)
        return output,n
    if mode=="stream":
        cur=c.execute(DENSE_SQL,(q,));stream=Stream(cur,len(sign))
        result,_=read("one",stream,sign,up,ix,2048,policy)
        cur.close();return result,stream.fetched
    cur=c.execute(JOIN_SQL,(t,q)) if mode=="sql" else c.execute(FINAL_SQL,(q,))
    output=[];count=0;left=2048
    try:
        while page:=cur.fetchmany(16):
            count+=len(page)
            for node,price in page:
                if price<=left:
                    output.append(node);left-=price
                    if not left:return output,count
                elif policy=="prefix":return output,count
        return output,count
    finally:cur.close()


def bench():
    build_rec=load(HERE/"sqlite-build.json");assert sha(DB)==build_rec["db_sha"]
    c=sqlite3.connect(DB.as_uri()+"?mode=ro",uri=True);c.execute("pragma query_only=on");c.execute("pragma cache_size=-65536")
    data=fixture()
    panel=select(r["q"] for t in data for r in t["queries"])
    track={};prep=[];q=0
    for t,tr in enumerate(data):
        start=time.perf_counter_ns();pairs=c.execute(COLS_SQL,(t,)).fetchall()
        a=np.asarray([r[0] for r in pairs]);prices=np.asarray([r[1] for r in pairs],dtype=int);ix=index(a,prices)
        stop=time.perf_counter_ns();assert a.tolist()==tr["prior"] and prices.tolist()==tr["costs"]
        sig=np.asarray(tr["signal"]);upper=suffix_bounds(sig)
        prep.append({"t":tr["t"],"rows":len(pairs),"ns":stop-start})
        for row in sorted(tr["queries"],key=lambda r:r["q"]):
            track[row["q"]]=(q,t,tr["t"],sig,upper,ix,row["expected"]);q+=1
    assert q==2000 and len(panel)==256
    # Global warmup primes the identical indexed data before the paired timing panel.
    obs=[];timings=[];rng=random.Random(68021)
    for code in sorted(track):
        q,t,tid,s,u,ix,expect=track[code]
        rec={"q":code,"t":tid,"n":len(s),"rows":{}}
        for p in ("prefix","skip"):
            for m in METHODS:
                got,n=execute(c,q,t,s,u,ix,p,m);assert got==expect[p],(code,p,m)
                rec["rows"][p+"/"+m]=n
        obs.append(rec)
    for code in sorted(panel):
        q,t,tid,s,u,ix,expect=track[code]
        for rep in range(7):
            order=[(p,m) for p in ("prefix","skip") for m in METHODS];rng.shuffle(order);marks={}
            for p,m in order:
                start=time.perf_counter_ns();got,n=execute(c,q,t,s,u,ix,p,m);end=time.perf_counter_ns()
                assert got==expect[p]
                marks[p+"/"+m]=end-start
            timings.append({"q":code,"t":tid,"rep":rep,"order":["/".join(v) for v in order],"ns":marks})
    c.close()
    put(HERE/"sqlite-queries.json.gz",obs);put(HERE/"sqlite-timing.json.gz",timings);put(HERE/"sqlite-static.json.gz",prep)
    by=defaultdict(list)
    for r in timings:by[r["q"]].append(r)
    med={q:{"t":v[0]["t"],**{k:statistics.median(r["ns"][k] for r in v) for k in v[0]["ns"]}} for q,v in by.items()}
    summary={}
    for p in ("prefix","skip"):
        vq=np.median([z[p+"/vector"] for z in med.values()])
        for m in METHODS:
            key=p+"/"+m;xs=np.asarray([z[key] for z in med.values()])/1000.
            summary[key]={"rows":sum(r["rows"][key] for r in obs),"median_us":float(np.median(xs)),"p95_us":float(np.quantile(xs,.95)),
              "ratio":float(np.median(xs)*1000/vq),"ratio_ci":boot_ratio(med,p,m) if m!="vector" else [1.,1.]}
    put(HERE/"sqlite-results.json",{"summary":summary,"prep_median_us":float(np.median([v["ns"] for v in prep]))/1000,"static_rows":sum(v["rows"] for v in prep),
        "cache_kib":65536,"reps":7,"comparisons":len(obs)*8,"timed_q":len(med),"timed_t":len({r["t"] for r in med.values()}),"page_rows":16,
        "files":{n:sha(HERE/n) for n in ("sqlite-queries.json.gz","sqlite-timing.json.gz","sqlite-static.json.gz","sqlite-build.json","SQL_PROTOCOL_RU.md","sqlite_test.py")}})
    print("Matched",len(obs)*8,"real SQLite output sequences.",flush=True)


if __name__=="__main__":{"build":build,"bench":bench}[sys.argv[1]]()

