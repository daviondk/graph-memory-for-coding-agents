"""SQLite measurements with physical storage accounting and balanced paired trials."""
from pathlib import Path
from collections import defaultdict
from statistics import mean,median
from time import perf_counter_ns as clock
import gzip,hashlib,json,os,platform,random,shutil,sqlite3,sys
import numpy as np
import greedy_sql as g

D=Path(__file__).resolve().parent
PRIVATE=Path(os.environ.get("PACK_BUDGET_HOME","D:/CodexResearch/x20-isetrace-fine-train/physical-budget"))
DB=PRIVATE/"store.sqlite"
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):
    b=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()+b"\n"
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def fixture():
    lock=read(D/"fixtures.json");data=[]
    for n,h,*_ in lock["files"]:
        assert sha(D/n)==h;data+=read(D/n)
    assert len({r["q"] for r in data})==len({r["t"] for r in data})==192
    return sorted(data,key=lambda r:r["q"])

def connection(path=DB):
    c=sqlite3.connect(path,timeout=30,isolation_level=None,cached_statements=64)
    c.execute("pragma cache_size=-49152");c.execute("pragma mmap_size=0");c.execute("pragma temp_store=memory")
    c.execute("pragma synchronous=FULL")
    return c

def build():
    PRIVATE.mkdir(parents=True,exist_ok=True)
    if DB.exists():
        if (D/"build.json").exists() and read(D/"build.json")["sqlite_rows"]==sum(len(r["items"]) for r in fixture()):return
        raise RuntimeError("Choose a new PACK_BUDGET_HOME for a fresh build; the existing DB was preserved")
    DATA=fixture();c=connection();c.execute("pragma journal_mode=WAL")
    c.execute("create table blocks(q integer not null,j integer not null,neg real not null,c integer not null,e integer not null,l integer not null,h integer not null,unique(q,j))")
    c.execute("create table answers(q integer not null,budget integer not null,body blob not null,primary key(q,budget)) without rowid")
    st=clock();c.execute("begin immediate")
    for i,r in enumerate(DATA):
        c.executemany("insert into blocks values(?,?,?,?,?,?,?)",[(i,v[0],-v[1],*v[3:]) for v in r["items"]])
    c.execute("commit");raw_time=clock()-st
    st=clock();c.execute("begin immediate");c.execute("create index idx_priority on blocks(q,neg,j,c,e,l,h)");c.execute("commit")
    index_time=clock()-st;st=clock();c.execute("begin immediate");picks=0
    for i,r in enumerate(DATA):
        items=[g.row(v) for v in r["items"]]
        for b in g.BUDGETS:
            selected,n=g.rebuild(c,i,r["core"],b)
            assert selected==g.greedy(items,r["core"],b)
            if b==2048:assert [v[1] for v in selected]==r["strict2048"]
            c.execute("insert into answers values(?,?,?)",(i,b,json.dumps(selected,separators=(",",":")).encode()))
            picks+=len(selected)
    c.execute("commit");cache_time=clock()-st
    c.execute("pragma wal_checkpoint(truncate)")
    plans={name:[row[-1] for row in c.execute("explain query plan "+sql,params)] for name,sql,params in (("scan_sort",g.SCAN,(0,)),("priority",g.INDEX,(0,)),("suffix",g.SUFFIX,(0,0,0)))}
    assert any("TEMP B-TREE" in t for t in plans["scan_sort"])
    assert all("TEMP B-TREE" not in t for t in plans["priority"]+plans["suffix"])
    assert any("COVERING INDEX" in t for t in plans["priority"])
    storage={k:{"pages":n,"bytes":b,"payload_bytes":t} for k,n,b,t in c.execute("select name,count(*),sum(pgsize),sum(payload) from dbstat group by name")}
    c.close()
    save(D/"build.json",{"sqlite_version":sqlite3.sqlite_version,"python":sys.version,"platform":platform.platform(),"sqlite_rows":sum(len(r["items"]) for r in DATA),
        "questions":192,"budgets":g.BUDGETS,"selected_items":picks,"build_ns":{"insert_rows":raw_time,"create_covering_index":index_time,"build_verify_and_materialize_answers":cache_time},
        "storage":storage,"file_bytes":DB.stat().st_size,"plans":plans,"fixtures":sha(D/"fixtures.json"),"initial_db_sha":sha(DB)})

def static():
    DATA=fixture();results=[];randomizer=random.Random(13);warm=connection()
    warm.execute("select sum(c) from blocks indexed by idx_priority").fetchone()
    jobs=[(b,i) for b in g.BUDGETS for i in range(len(DATA))]
    for label,reps in (("sqlite-cold",1),("warm",5)):
        for rep in range(reps):
            randomizer.shuffle(jobs)
            for b,i in jobs:
                r=DATA[i]
                methods=["scan_sort","priority","materialized"];randomizer.shuffle(methods)
                for m in methods:
                    c=connection() if label=="sqlite-cold" else warm
                    tic=clock()
                    if m=="materialized":
                        picked,nbytes=g.cached(c,i,b);n=1
                    else:
                        picked,n=g.rebuild(c,i,r["core"],b,g.SCAN if m=="scan_sort" else g.INDEX);nbytes=None
                    ns=clock()-tic
                    assert [v[1] for v in picked]==[v[1] for v in g.cached(warm,i,b)[0]]
                    results.append([label,rep,i,b,m,ns,n,nbytes])
                    if label=="sqlite-cold":c.close()
    warm.close();save(D/"static-times.json.gz",results)

def store_full(c,i,b,new):
    body=json.dumps(new,separators=(",",":")).encode()
    cur=c.execute("update answers set body=? where q=? and budget=? and body!=?",(body,i,b,body))
    return len(body) if cur.rowcount else 0

def dynamic():
    DATA=fixture();c=connection();rng=random.Random(13);all_results=[];n=len(DATA)
    for rep in range(3):
        jobs=[(i,b) for i in range(n) for b in g.BUDGETS];rng.shuffle(jobs)
        for i,b in jobs:
            r=DATA[i];core=r["core"];items=r["items"];base=[g.row(v) for v in items]
            original,_=g.cached(c,i,b);cases=list(g.CASES);rng.shuffle(cases)
            for case in cases:
                changes=g.changes(items,original,case,r["q"],b)
                c.execute("savepoint fixture")
                old=original
                if case=="insert1":
                    j=changes[0][1][1];c.execute("delete from blocks where q=? and j=?",(i,j))
                    old,_=g.rebuild(c,i,core,b);c.execute("update answers set body=? where q=? and budget=?",(json.dumps(old,separators=(",",":")).encode(),i,b))
                src={v[1]:v for v in base}
                for _,v in changes:src[v[1]]=v
                want=g.greedy(src.values(),core,b)
                tic=clock();g.write(c,i,changes);write_ns=clock()-tic
                modes=["rebuild","repair"];rng.shuffle(modes)
                for m in modes:
                    c.execute("savepoint answer")
                    tic=clock()
                    if m=="rebuild":
                        bytes_in=0;new,rows=g.rebuild(c,i,core,b);branch="full"
                        bytes_out=store_full(c,i,b,new)
                    else:
                        previous,bytes_in=g.cached(c,i,b)
                        new,rows,branch=g.repair(c,i,core,b,previous,changes)
                        bytes_out=g.persist(c,i,b,previous,new)
                    elapsed=clock()-tic
                    assert new==want
                    all_results.append([rep,i,b,case,m,branch,len(changes),write_ns,elapsed,rows,bytes_in,bytes_out,old!=new,[v[1] for v in old]!=[v[1] for v in new]])
                    c.execute("rollback to answer");c.execute("release answer")
                c.execute("rollback to fixture");c.execute("release fixture")
        print("dynamic replicate",rep+1,flush=True)
        save(D/f"dynamic-rep{rep+1}.json.gz",[z for z in all_results if z[0]==rep])
    for i,r in enumerate(DATA):
        assert set(c.execute("select "+g.PROJECTION+" from blocks where q=?",(i,)))==set(g.row(v) for v in r["items"])
        for b in g.BUDGETS:assert g.cached(c,i,b)[0]==g.greedy([g.row(v) for v in r["items"]],r["core"],b)
    c.close()
    save(D/"dynamic-complete.json",{"reps":[sha(D/f"dynamic-rep{k}.json.gz") for k in (1,2,3)],"total":len(all_results)})

def durability():
    DATA=fixture();runs=[]
    for mode in ("raw","covered","cached-rebuild","cached-repair"):
        path=PRIVATE/("durable-"+mode+".sqlite")
        if path.exists():raise RuntimeError("Durability DB already exists; preserve the original and choose a fresh target before rerunning")
        shutil.copyfile(DB,path)
        c=connection(path);c.execute("pragma journal_mode=WAL");c.execute("pragma wal_autocheckpoint=0")
        if mode=="raw":c.execute("drop index idx_priority")
        if mode in ("raw","covered"):c.execute("drop table answers")
        if mode.startswith("cached"):c.execute("delete from answers where budget!=2048")
        c.execute("pragma wal_checkpoint(truncate)")
        order=list(range(len(DATA)));random.Random(13).shuffle(order);b=2048
        for i in order:
            r=DATA[i];base=[g.row(v) for v in r["items"]];old=g.greedy(base,r["core"],b);update=g.changes(r["items"],old,"random1",r["q"],b)
            tic=clock();c.execute("begin immediate");g.write(c,i,update);data_ns=clock()-tic;start=clock();rows=None
            written=0
            if mode.startswith("cached"):
                if mode=="cached-repair":
                    prev,_=g.cached(c,i,b);new,rows,_=g.repair(c,i,r["core"],b,prev,update)
                    written=g.persist(c,i,b,prev,new)
                else:
                    new,rows=g.rebuild(c,i,r["core"],b);written=store_full(c,i,b,new)
            cache_ns=clock()-start;start=clock();c.execute("commit");commit_ns=clock()-start
            runs.append([mode,i,len(update),data_ns,cache_ns,commit_ns,clock()-tic,rows,written])
        wal=Path(str(path)+"-wal");pages=wal.stat().st_size if wal.exists() else 0
        c.execute("pragma wal_checkpoint(truncate)");c.close()
        save(D/("durable-"+mode+".json"),{"wal_bytes_before_checkpoint":pages,"size":path.stat().st_size,"transactions":len(order),"synchronous":"FULL","budget":2048,
              "results":[r for r in runs if r[0]==mode],"description":"one autocommitted transaction per question, fixed seed order"})
    print("durability",len(runs),flush=True)

if __name__=="__main__":
    {"build":build,"static":static,"dynamic":dynamic,"durability":durability}[sys.argv[1]]()

