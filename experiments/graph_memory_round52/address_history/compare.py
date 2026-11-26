"""Address-only as-of histories with score reconstruction from term activation receipts."""
from pathlib import Path
import hashlib
import json
import gzip
import os
import sqlite3
import struct
import sys
from tempfile import TemporaryDirectory

D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"maintenance"))
from engine import BASE_SCHEMA,advance,connect,create_base

PLANS=("scan","partial","eligible","journal","thin","address")
TEMP_ROOT=Path(os.environ.get("R52_HISTORY_WORK","D:/CodexResearch/x20-r52-address-history"))
from address_store import plan_setup,read_pair

def bits(value):return struct.pack("<d",value)

def oracle(candidates,t):
    id,_,b,u,seen=min(candidates,key=lambda c:(-(c[3] if c[4] is not None and c[4]<=t else c[2]),c[1],c[0]))
    return id,(u if seen is not None and seen<=t else b)

def fixture(plan):
    db=connect(":memory:");db.executescript(BASE_SCHEMA)
    db.execute("INSERT INTO cursor(q) VALUES(0)")
    # At t=1 B overtakes A; A's boost restores A in the same atomic version.
    db.executemany("INSERT INTO c VALUES(0,?,?,?,?,NULL)",[(0,0,5.,9.),(1,1,4.,8.),(2,1,2.,10.),(3,0,1.,10.)])
    plan_setup(db,plan)
    for t,group in [(1,[1,0]),(2,[2]),(3,[3])]:
        advance(db,0,t,group);advance(db,0,t,group)
    assert [db.execute(read_pair(plan),(0,t)).fetchone() for t in range(4)]==[(0,5.),(0,9.),(2,10.),(3,10.)]
    if plan=="address":
        assert db.execute("SELECT step,id FROM history ORDER BY step").fetchall()==[(0,0),(2,2),(3,3)]
    db.close()

def work(plan,data,base,dest):
    import shutil
    shutil.copyfile(base,dest);db=connect(dest);plan_setup(db,plan)
    sql=read_pair(plan);proof=hashlib.sha256();audited=changes=events=0
    for q,e in enumerate(data):
        cs=e["candidates"];states=[oracle(cs,t) for t in range(e["cuts"]+1)]
        for k in range(1,e["cuts"]+1):
            now=[c[0] for c in cs if c[4]==k]
            advance(db,q,k,now);events+=1
            changes+=int(states[k-1][0]!=states[k][0])
            for t in range(k+1):
                i,v=db.execute(sql,(q,t)).fetchone();g,x=states[t]
                if i!=g or bits(v)!=bits(x):raise AssertionError((plan,q,k,t,i,v,g,x))
                proof.update(struct.pack("<IIIId",q,k,t,i,v));audited+=1
    assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
    is_hist=plan in ("journal","thin","address")
    histories=None
    if is_hist:
        tuples=db.execute("SELECT q,step,id FROM history ORDER BY q,step").fetchall()
        histories=hashlib.sha256(b"".join(struct.pack("<III",*r) for r in tuples)).hexdigest()
        rows=len(tuples)
    else:rows=0
    if plan=="address":assert rows==len(data)+changes
    # Roll back a candidate mutation after triggers have fired.
    probe=db.execute("SELECT q,id FROM c WHERE seen IS NULL ORDER BY q,id LIMIT 1").fetchone()
    db.execute("BEGIN IMMEDIATE");db.execute("UPDATE c SET seen=10000 WHERE q=? AND id=?",probe)
    db.execute("UPDATE cursor SET upto=10000 WHERE q=?",probe[:1]);db.rollback()
    assert db.execute("SELECT seen FROM c WHERE q=? AND id=?",probe).fetchone()==(None,)
    if is_hist:assert db.execute("SELECT count(*) FROM history").fetchone()[0]==rows
    assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]==0
    db.close();physical=dest.stat().st_size
    db=connect(dest)
    for q,e in enumerate(data):
        assert db.execute(sql,(q,e["cuts"])).fetchone()==oracle(e["candidates"],e["cuts"])
    db.execute("VACUUM");db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.close()
    return dict(reads=audited,updates=events,changes=changes,rows=rows,digest=proof.hexdigest(),
                timeline_digest=histories,full_db_bytes=physical,vacuum_db_bytes=dest.stat().st_size)

def main():
    source=D.parent/"maintenance"/"workload.json.gz"
    data=json.loads(gzip.decompress(source.read_bytes()));TEMP_ROOT.mkdir(parents=True,exist_ok=True)
    result={}
    with TemporaryDirectory(dir=TEMP_ROOT) as folder:
        folder=Path(folder);base=folder/"base.sqlite";create_base(base,enumerate(data))
        for name in PLANS:
            fixture(name)
            result[name]=work(name,data,base,folder/(name+".sqlite"))
    assert len({z["digest"] for z in result.values()})==1
    assert result["thin"]["timeline_digest"]==result["journal"]["timeline_digest"]
    assert result["address"]["rows"]==4592 and result["journal"]["rows"]==5822
    out=dict(plans=result,n=len(data),source=hashlib.sha256(source.read_bytes()).hexdigest(),sqlite=sqlite3.sqlite_version,
             protocol=hashlib.sha256((D/"PROTOCOL_RU.md").read_bytes()).hexdigest())
    (D/"results.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf8")
    print({k:(v["rows"],v["full_db_bytes"],v["vacuum_db_bytes"]) for k,v in result.items()})
if __name__=="__main__":main()

