"""Independent SQL co-occurrence oracle, transaction failure and exact replay after reopening."""
from collections import Counter,deque
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from benchmark import HERE,MODES,chosen,panels,save
from store import Store,decode

def expect_reject(call,error,message):
    try:call()
    except error as exc:
        assert message in str(exc)
    else:raise AssertionError("unexpectedly accepted")

def oracle_db():
    db=sqlite3.connect(":memory:",isolation_level=None)
    db.executescript("""
    CREATE TABLE edge(file INTEGER, event INTEGER, PRIMARY KEY(file,event)) WITHOUT ROWID;
    CREATE INDEX incident ON edge(event,file);
    CREATE TABLE tie(file INTEGER PRIMARY KEY,n INTEGER);
    """)
    return db

def sql_rank(db,anchor):
    return db.execute("""
    WITH joint AS (
      SELECT b.file AS file, count(*) AS score FROM edge a
      JOIN edge b ON a.event=b.event WHERE a.file=? GROUP BY b.file
    )
    SELECT t.file, coalesce(joint.score,0) AS n FROM tie t LEFT JOIN joint ON t.file=joint.file
    WHERE t.file<>? ORDER BY n DESC,t.n DESC,t.file ASC LIMIT 8
    """,(anchor,anchor)).fetchall()

def persisted(st):
    names=["event","post"]+(["live","cold_file"] if st.mode=="split" else [])
    return {name:st.db.execute("SELECT * FROM "+name+" ORDER BY 1,2" if name in ("event","post")
            else "SELECT * FROM "+name+" ORDER BY 1").fetchall() for name in names}

def synthetic(folder,mode):
    path=folder/(mode+".sqlite")
    store=Store(path,mode,True)
    sql=oracle_db()
    # Nine events share both 0 and 1. The oldest loses its last owner on the ninth insertion.
    seq=[(0,1)]*9+[(0,2,5),(0,1,2,4),(0,1),(3,7),(6,7,8)]
    freq=Counter({f:9-f for f in range(10)})
    sql.executemany("INSERT INTO tie VALUES(?,?)",freq.items())
    prior=sorted(freq,key=lambda f:(-freq[f],f))[:9]
    replays=faults=collisions=gaps=sql_matches=0
    for j,ids in enumerate(seq):
        if j in (0,8,11):
            prior_snapshot=persisted(store)
            expect_reject(lambda:store.append(j,"sha"+str(j),ids,True),RuntimeError,"rollback");faults+=1
            assert store.next_id==j and persisted(store)==prior_snapshot
            for f in (-1,*freq):
                assert store.read(f,freq,prior)[0]==sql_rank(sql,f)
                sql_matches+=1
        if j in (1,9):
            old=store.owned.get(0,())
            store.close();store=Store(path,mode)
            assert store.next_id==j
            if mode=="own":assert old and not store.owned
        assert store.append(j,"sha"+str(j),ids)
        sql.executemany("INSERT INTO edge VALUES(?,?)",((f,j) for f in ids))
        assert not store.append(j,"sha"+str(j),ids)
        replays+=1
        expect_reject(lambda:store.append(j,"changed",ids),ValueError,"conflicting");collisions+=1
        expect_reject(lambda:store.append(j,"sha"+str(j),tuple(reversed(ids))),ValueError,"conflicting");collisions+=1
        expect_reject(lambda:store.append(j+2,"future",ids),ValueError,"gap");gaps+=1
        for f in (-1,*freq):
            assert store.read(f,freq,prior)[0]==sql_rank(sql,f)
            sql_matches+=1
    store.close();sql.close()
    return dict(sql_matches=sql_matches,replays=replays,faults=faults,collisions=collisions,gaps=gaps,mid_reopens=2)

def real(folder,mode,panel,repo,rows):
    path=folder/"recovery.sqlite"
    store=Store(path,mode,True)
    sql=oracle_db()
    ids={};freq=Counter();window=deque()
    q=post_queries=new_ids=0
    split=len(rows)//2;j=0
    for t,(rev,paths) in enumerate(rows):
        if t==split:
            store.close();store=Store(path,mode)
            assert store.next_id==j
            recovery_rows=store.restore_rows;recovery_payload=store.restore_payload
        if len(paths)>64:paths=[]
        name=chosen(panel,rev,t,len(rows),paths)
        if name is not None:
            anchor=ids.get(name,-1)
            prior=sorted(range(len(ids)),key=lambda f:(-freq[f],f))[:9]
            exact=sql_rank(sql,anchor)
            assert store.read(anchor,freq,prior)[0]==exact,(mode,panel,repo,t)
            q+=1
            post_queries+=t>=split
        codes=[]
        for p in paths:
            if p not in ids:
                ids[p]=len(ids)
                sql.execute("INSERT INTO tie VALUES(?,0)",(ids[p],))
                new_ids+=t>=split
            codes.append(ids[p])
        if len(window)==32:
            old=window.popleft()
            freq.subtract(old)
            sql.executemany("UPDATE tie SET n=n-1 WHERE file=?",((f,) for f in old))
        freq.update(codes);window.append(codes)
        sql.executemany("UPDATE tie SET n=n+1 WHERE file=?",((f,) for f in codes))
        if len(codes)>=2:
            assert store.append(j,rev,codes)
            sql.executemany("INSERT INTO edge VALUES(?,?)",((f,j) for f in codes))
            j+=1
    db_events=store.db.execute("SELECT j,members FROM event ORDER BY j").fetchall()
    for event,blob in db_events:
        assert sorted(decode(blob))==[r[0] for r in sql.execute("SELECT file FROM edge WHERE event=? ORDER BY file",(event,))]
    assert len(db_events)==j
    result=dict(events=j,sql_matches=q,post_restart_matches=post_queries,
                post_restart_new_path_ids=new_ids,restart_rows=recovery_rows,restart_payload=recovery_payload,
                lazy_reads_after_reopen=store.restore_rows-recovery_rows)
    store.close();path.unlink();sql.close()
    return result

def main():
    data=panels();out={"synthetic":{},"real":{}}
    with TemporaryDirectory(dir=HERE,prefix="correctness-") as folder:
        folder=Path(folder)
        for mode in MODES:
            out["synthetic"][mode]=synthetic(folder,mode)
            out["real"][mode]={}
            for panel in ("B","long"):
                out["real"][mode][panel]={repo:real(folder,mode,panel,repo,rs) for repo,rs in data[panel].items()}
    save(HERE/"correctness.json",out)
    print({m:out["synthetic"][m] for m in MODES})
    print([(mode,sum(v["post_restart_matches"] for reps in p.values() for v in reps.values()))
           for mode,p in out["real"].items()])
if __name__=="__main__":main()
