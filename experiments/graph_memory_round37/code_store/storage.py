"""Three SQLite representations of an independent one-edit memory transition."""
import sqlite3
from collections import defaultdict,deque
from inputs import cap

def rows(values):return [(n,bytes.fromhex(s)) for n,s in values]

def material(path,base,seen,start,end,delta):
    carry={}
    if start is not None:
        for n,s in base:
            if n<start:j=n
            elif n>end:j=n+delta
            else:continue
            if j not in seen:carry[j]=s
    return cap(path,carry,128-len(seen))|seen

def initialize(path,kind,inputs):
    db=sqlite3.connect(path,isolation_level=None,cached_statements=64)
    assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0]=="wal"
    db.execute("PRAGMA synchronous=NORMAL");db.execute("PRAGMA wal_autocheckpoint=0");db.execute("PRAGMA cache_size=-8192")
    if kind=="M":
        db.executescript("CREATE TABLE f(rid INTEGER PRIMARY KEY,e INTEGER NOT NULL,n INTEGER NOT NULL,s BLOB NOT NULL); CREATE INDEX fn ON f(e,n);")
    else:
        db.execute("CREATE TABLE f(e INTEGER NOT NULL,n INTEGER NOT NULL,s BLOB NOT NULL,PRIMARY KEY(e,n)) WITHOUT ROWID")
    if kind=="L":
        db.execute("CREATE TABLE v(e INTEGER PRIMARY KEY,k INTEGER,z INTEGER,d INTEGER)")
        db.execute("CREATE TABLE r(e INTEGER NOT NULL,n INTEGER NOT NULL,s BLOB NOT NULL,PRIMARY KEY(e,n)) WITHOUT ROWID")
    db.execute("BEGIN")
    db.executemany("INSERT INTO f(e,n,s) VALUES (?,?,?)",((i,n,s) for i,item in inputs.items() for n,s in item["base"]))
    db.commit()
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    return db

def update_absolute(db,e,old,desired):
    before=dict(old)
    db.executemany("DELETE FROM f WHERE e=? AND n=?",((e,n) for n in before if n not in desired))
    db.executemany("UPDATE f SET s=? WHERE e=? AND n=?",((s,e,n) for n,s in desired.items() if n in before and s!=before[n]))
    db.executemany("INSERT INTO f(e,n,s) VALUES (?,?,?)",((e,n,s) for n,s in desired.items() if n not in before))

def update_slots(db,e,previous,desired):
    fixed={n for i,n,s in previous if desired.get(n)==s}
    free=[(i,n,s) for i,n,s in previous if n not in fixed]
    # Pair equal digests first. Any assignment of the rest attains max(deletions, additions).
    new={n:s for n,s in desired.items() if n not in fixed}
    targets=defaultdict(deque)
    for n,s in new.items():targets[s].append(n)
    rewrite=[];spare=[];taken=set()
    for i,n,s in free:
        if targets[s]:
            dest=targets[s].popleft();taken.add(dest);rewrite.append((dest,s,i))
        else:spare.append(i)
    need=[(n,s) for n,s in new.items() if n not in taken]
    paired=min(len(spare),len(need))
    rewrite.extend((n,s,i) for i,(n,s) in zip(spare,need))
    db.executemany("UPDATE f SET n=?,s=? WHERE rid=?",rewrite)
    db.executemany("DELETE FROM f WHERE rid=?",((i,) for i in spare[paired:]))
    db.executemany("INSERT INTO f(e,n,s) VALUES (?,?,?)",((e,n,s) for n,s in need[paired:]))
    return max(len(free),len(new))

def transition(db,kind,e,item):
    db.execute("BEGIN IMMEDIATE")
    before=db.total_changes
    read=0
    try:
        if kind=="L":
            db.execute("INSERT INTO v(e,k,z,d) VALUES (?,?,?,?)",(e,item["start"],item["end"],item["delta"]))
            db.executemany("INSERT INTO r(e,n,s) VALUES (?,?,?)",((e,n,s) for n,s in item["receipt"].items()))
        else:
            previous=db.execute("SELECT n,s FROM f WHERE e=?" if kind=="A" else "SELECT rid,n,s FROM f WHERE e=?",(e,)).fetchall()
            base=previous if kind=="A" else [(n,s) for _,n,s in previous]
            read=len(previous)
            goal=material(item["path"],base,item["receipt"],item["start"],item["end"],item["delta"])
            if kind=="A":
                update_absolute(db,e,previous,goal)
            else:
                lower=update_slots(db,e,previous,goal)
                assert db.total_changes-before==lower
        db.commit()
    except Exception:
        db.rollback();raise
    return db.total_changes-before,read,int(kind!="L")

LAZY_QUERY="""SELECT 0,k,z,d,NULL FROM v WHERE e=?1
UNION ALL SELECT 1,n,NULL,NULL,s FROM f WHERE e=?1 AND EXISTS (SELECT 1 FROM v WHERE e=?1 AND k IS NOT NULL)
UNION ALL SELECT 2,n,NULL,NULL,s FROM r WHERE e=?1"""

def lookup(db,kind,e,item):
    if kind!="L":
        got=db.execute("SELECT n,s FROM f WHERE e=? ORDER BY n",(e,)).fetchall()
        return got,len(got)
    received=db.execute(LAZY_QUERY,(e,)).fetchall()
    tag,start,end,delta,_=received[0]
    assert tag==0
    base=[];seen={}
    for tag,n,_,_,s in received[1:]:
        if tag==1:base.append((n,s))
        else:
            assert tag==2;seen[n]=s
    goal=material(item["path"],base,seen,start,end,delta)
    return sorted(goal.items()),len(received)
