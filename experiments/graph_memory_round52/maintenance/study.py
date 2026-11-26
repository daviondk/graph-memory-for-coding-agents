"""Benchmark matched SQLite episode transactions on repeated write/read workloads."""
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns as clock

from engine import PLANS, advance, connect, create_base, setup, statement
from source import ROOT,SCRATCH,blocks,prepare,read,schedule,sha,winner,write

MODES=(0,1,8)
REPEATS=4

def state_digest(db):
    rows=db.execute("SELECT q,id,seen FROM c WHERE seen IS NOT NULL ORDER BY q,id").fetchall()
    cursor=db.execute("SELECT q,upto FROM cursor ORDER BY q").fetchall()
    return hashlib.sha256(json.dumps([rows,cursor],separators=(",",":")).encode()).hexdigest()

def size(db):
    pages=db.execute("PRAGMA page_count").fetchone()[0]
    page_bytes=db.execute("PRAGMA page_size").fetchone()[0]
    return {"database":[pages,pages*page_bytes]}

def execute_block(db,plan,mode,events):
    live,asof=statement(plan,True),statement(plan,False)
    outputs=[];write_ns=0;read_ns=0
    tic=clock()
    for q,k,added,samples,expected in events:
        t=clock();advance(db,q,k,added);write_ns+=clock()-t
        if mode:
            t=clock()
            db.execute("BEGIN")
            if mode==1:
                outputs.append(db.execute(live,(q,k)).fetchone()[0])
            else:
                for cutoff,_ in samples[:mode]:
                    outputs.append(db.execute(live if cutoff==k else asof,(q,cutoff)).fetchone()[0])
            db.commit()
            read_ns+=clock()-t
    elapsed=clock()-tic
    target=[a for q,k,added,samples,end in events for a in (() if mode==0 else (end,) if mode==1 else (v for _,v in samples[:mode]))]
    assert outputs==target
    return [elapsed,write_ns,read_ns]

def exhaustive(data):
    # A real SQLite transaction for every prefix, followed by ALL historical reads at that stage.
    out={}
    for plan in PLANS:
        db=connect(":memory:");db.execute("PRAGMA foreign_keys=ON")
        from engine import BASE_SCHEMA
        db.executescript(BASE_SCHEMA)
        db.executemany("INSERT INTO cursor(q) VALUES(?)",[(q,) for q in range(len(data))])
        db.executemany("INSERT INTO c VALUES(?,?,?,?,?,NULL)",[(q,i,r,b,u) for q,e in enumerate(data) for i,r,b,u,s in e["candidates"]])
        setup(db,plan)
        counts=[0,0,0,0]
        for q,e in enumerate(data):
            a=e["candidates"];targets=[winner(a,t) for t in range(e["cuts"]+1)]
            assert targets[-1]==e["terminal"]
            counts[0]+=1
            for k in range(1,e["cuts"]+1):
                advance(db,q,k,[v[0] for v in a if v[4]==k]);counts[1]+=1
                for cut in range(k+1):
                    assert db.execute(statement(plan,cut==k),(q,cut)).fetchone()[0]==targets[cut]
                    counts[2]+=1
                if targets[k]!=targets[k-1]:counts[3]+=1
        if plan=="journal":
            history=db.execute("SELECT count(*) FROM history").fetchone()[0]
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        out[plan]=dict(episodes=counts[0],transactions=counts[1],reads=counts[2],id_changes=counts[3],
                       history_rows=history if plan=="journal" else None,digest=state_digest(db))
        db.close()
    assert len({x["digest"] for x in out.values()})==1
    return out

def fixture():
    from engine import BASE_SCHEMA
    snapshots=[]
    for plan in PLANS:
        db=connect(":memory:");db.executescript(BASE_SCHEMA)
        db.execute("INSERT INTO cursor(q) VALUES(1)")
        db.executemany("INSERT INTO c VALUES(1,?,?,?,?,NULL)",[(0,3,6.,9.),(1,1,5.,8.),(2,2,5.,8.),(3,0,3.,6.)])
        setup(db,plan)
        # Simultaneous equal boosted scores resolve by static priority; equal initial score can also win.
        for k,ids,target in [(1,[3],3),(2,[2,1],1),(3,[0],0)]:
            advance(db,1,k,ids)
            assert db.execute(statement(plan,True),(1,k)).fetchone()[0]==target
            advance(db,1,k,ids)
            assert db.execute(statement(plan,True),(1,k)).fetchone()[0]==target
        assert [db.execute(statement(plan,False),(1,k)).fetchone()[0] for k in range(4)]==[0,3,1,0]
        snapshots.append(state_digest(db));db.close()
    assert len(set(snapshots))==1

def extended(data,groups):
    result=[]
    for events in groups:
        block=[]
        for q,k,added,samples,end in events:
            e=data[q]
            rng=random.Random(f"r52-frontier|{e['panel']}|{e['q']}|{k}")
            extra=[rng.randrange(k) if i%2==0 else k for i in range(24)]
            targets=[winner(e["candidates"],t) for t in range(k+1)]
            block.append((q,k,added,tuple(samples)+tuple((t,targets[t]) for t in extra),end))
        result.append(block)
    return result

def run(frontier=False):
    data=read("workload.json.gz");seal=read("registration.json")
    assert sha((ROOT/"PROTOCOL_RU.md").read_bytes())==seal["protocol"]
    bs=blocks(data);groups=schedule(data,bs)
    assert sha(json.dumps(groups,separators=(",",":")).encode())==seal["schedule"]
    fixture()
    if frontier:
        groups=extended(data,groups)
        modes=(2,4,16,32); plans=("cover","partial","eligible","journal")
    else:
        modes=MODES;plans=PLANS
        write("correctness.json",exhaustive(data))
    SCRATCH.mkdir(exist_ok=True,parents=True)
    timings=[];identities=set()
    with TemporaryDirectory(dir=SCRATCH) as tmp:
        tmp=Path(tmp);base=tmp/"base.db"
        create_base(base,[(q,data[q]) for ids in bs for q in ids])
        for rep in range(REPEATS):
            arms=[(p,m) for p in plans for m in modes]
            order=list(range(len(bs)))
            random.Random(528954+rep+int(frontier)*9012).shuffle(arms);random.Random(528907+rep+int(frontier)*9012).shuffle(order)
            for position,(plan,mode) in enumerate(arms):
                dest=tmp/"visit.db"
                shutil.copyfile(base,dest)
                db=connect(dest)
                db.execute("SELECT sum(b+u) FROM c").fetchone()
                db.execute("SELECT sum(q) FROM cursor").fetchone()
                t=clock();setup(db,plan);db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone();build=clock()-t
                sqlplans={s:[list(row) for row in db.execute("EXPLAIN QUERY PLAN "+statement(plan,s=="live"),(0,1))]
                          for s in ("live","asof")}
                before=size(db)
                block_ms={i:execute_block(db,plan,mode,groups[i]) for i in order}
                t=clock();ck=db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone();finish=clock()-t
                assert ck[0]==0
                after=size(db);db.close()
                # Fresh connection sees the committed state and all final addresses.
                db=connect(dest);identity=state_digest(db);identities.add(identity)
                for ids in bs:
                    for q in ids:
                        got=db.execute(statement(plan,True),(q,data[q]["cuts"])).fetchone()[0]
                        assert got==data[q]["terminal"]
                n_hist=db.execute("SELECT count(*) FROM history").fetchone()[0] if plan=="journal" else None
                db.close()
                timings.append(dict(rep=rep,position=position,plan=plan,reads=mode,build_ns=build,checkpoint_ns=finish,
                                  blocks=block_ms,block_order=order,queries=sqlplans,before_pages=before,
                                  after_pages=after,history_rows=n_hist,identity=identity,db_bytes=dest.stat().st_size))
                dest.unlink()
            write("frontier-timings.json.gz" if frontier else "timings.json.gz",timings)
            print("finished repeat",rep+1,flush=True)
    assert len(identities)==1
    native=dict(python=sys.version,sqlite=sqlite3.sqlite_version,host=platform.platform(),
                machine=platform.machine(),processor=os.environ.get("PROCESSOR_IDENTIFIER",""),
                base_b=base_size(bs,data),n_blocks=len(bs),per_block=32,read_modes=MODES,repeats=REPEATS)
    if not frontier:write("environment.json",native)

def base_size(bs,data):
    return {"episodes":sum(map(len,bs)),"candidates":sum(len(data[q]["candidates"]) for ids in bs for q in ids)}

if __name__=="__main__":
    run("--frontier" in sys.argv)

