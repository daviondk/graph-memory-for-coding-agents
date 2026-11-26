"""SQLite-persistent operators with a shared warm read-through cache."""
import sqlite3
from bisect import bisect_left,bisect_right
from math import log1p
from struct import pack,unpack
from inputs import h

def compile_model(m):
    beta=m["coef"]
    return (m["intercept"],beta,tuple(tuple(v*log1p(n) for n in range(257)) for v in beta))

def select(model,base,nums,hist,receipt,k,end,delta,now):
    bias,beta,tables=model;prev,nv,ne=hist
    if k is None:middle=moved=0
    else:
        right=bisect_right(nums,end)
        middle=right-bisect_left(nums,k)
        moved=len(nums)-right if delta else 0
    same=sum(n in base for n in receipt)
    features=(len(base),len(receipt),same,moved,middle,abs(delta or 0),int(k is not None),now-prev,nv,ne)
    score=bias
    for j,n in enumerate(features):
        if j==6:score+=beta[j]*n
        elif n<=256:score+=tables[j][n]
        else:score+=beta[j]*log1p(n)
    return "L" if score>0 else "A"

def dbopen(path,mode,new=True):
    db=sqlite3.connect(path,isolation_level=None,cached_statements=64)
    if not new:return db
    assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0]=="wal"
    db.execute("PRAGMA synchronous=NORMAL");db.execute("PRAGMA wal_autocheckpoint=0");db.execute("PRAGMA cache_size=-8192")
    db.execute("CREATE TABLE f(e INTEGER NOT NULL,n INTEGER NOT NULL,s BLOB NOT NULL,PRIMARY KEY(e,n)) WITHOUT ROWID")
    if mode!="A":
        db.execute("CREATE TABLE v(e INTEGER PRIMARY KEY,k INTEGER,z INTEGER,d INTEGER)")
        db.execute("CREATE TABLE r(e INTEGER NOT NULL,n INTEGER NOT NULL,s BLOB NOT NULL,PRIMARY KEY(e,n)) WITHOUT ROWID")
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    return db

def ingest(db,mode,e,pairs,marker,prev):
    # Input digests are ordinary hex strings from the upstream view projection.
    base={n:bytes.fromhex(s) for n,s in pairs}
    nums=hist=None
    db.execute("BEGIN IMMEDIATE")
    try:
        if mode=="H":
            # The synthetic numeric marker stream contains all actual prior typed views/replaces of this path.
            hist=(prev,marker.count("v"),marker.count("e"))
            nums=tuple(sorted(base))
            db.execute("INSERT INTO f VALUES(?,0,?)",(e,pack(">III",*hist)))
        db.executemany("INSERT INTO f VALUES(?,?,?)",((e,n,s) for n,s in base.items()))
        db.commit()
    except Exception:
        db.rollback();raise
    return base,nums,hist

def material(path,base,receipt,k,end,delta):
    shifted={}
    if k is not None:
        for n,s in base.items():
            if n<k:j=n
            elif n>end:j=n+delta
            else:continue
            if j not in receipt:shifted[j]=s
    if len(shifted)+len(receipt)>128:
        order=sorted(shifted,key=lambda n:(h("R37-128|"+path+"|"+str(n)),n))
        shifted={n:shifted[n] for n in order[:128-len(receipt)]}
    return shifted|receipt

def static_write(db,e,before,after):
    db.executemany("DELETE FROM f WHERE e=? AND n=?",((e,n) for n in before if n not in after))
    db.executemany("UPDATE f SET s=? WHERE e=? AND n=?",((s,e,n) for n,s in after.items() if n in before and before[n]!=s))
    db.executemany("INSERT INTO f VALUES(?,?,?)",((e,n,s) for n,s in after.items() if n not in before))

def edit(db,mode,model,e,old,inp):
    receipt={n:bytes.fromhex(s) for n,s in inp["receipt"]}
    path,k,end,delta=inp["path"],inp["start"],inp["end"],inp["delta"]
    prep_select=0;prep_rows=0
    if old is None:
        base=nums=hist=None
        if mode!="L":
            rows=db.execute("SELECT n,s FROM f WHERE e=? ORDER BY n",(e,)).fetchall()
            prep_select=1;prep_rows=len(rows)
            if mode=="H":
                assert rows[0][0]==0
                hist=unpack(">III",rows[0][1]);base=dict(rows[1:]);nums=tuple(base)
            else:base=dict(rows)
    else:base,nums,hist=old
    picked=select(model,base,nums,hist,receipt,k,end,delta,inp["current"]) if mode=="H" else mode
    db.execute("BEGIN IMMEDIATE")
    try:
        if picked=="A":
            after=material(path,base,receipt,k,end,delta)
            static_write(db,e,base,after)
            state=("A",after)
        else:
            db.execute("INSERT INTO v VALUES(?,?,?,?)",(e,k,end,delta))
            db.executemany("INSERT INTO r VALUES(?,?,?)",((e,n,s) for n,s in receipt.items()))
            state=("L",(path,base,receipt,k,end,delta)) if base is not None else None
        db.commit()
    except Exception:
        db.rollback();raise
    return picked,state,prep_select,prep_rows

# A single SQL trip resolves the persisted route and retrieves positive-address rows.
QUERY="""SELECT 2,k,z,d,NULL FROM v WHERE e=?1
UNION ALL SELECT 0,n,NULL,NULL,s FROM f WHERE e=?1 AND n>0
     AND NOT EXISTS(SELECT 1 FROM v WHERE e=?1 AND k IS NULL)
UNION ALL SELECT 1,n,NULL,NULL,s FROM r WHERE e=?1"""

def answer(db,mode,e,path,state):
    if state is not None:
        k,x=state
        if k=="ready":return x,0,0
        goal=x if k=="A" else material(*x)
        return tuple(sorted(goal.items())),0,0
    if mode=="A":
        got=db.execute("SELECT n,s FROM f WHERE e=? AND n>0 ORDER BY n",(e,)).fetchall()
        return tuple(got),1,len(got)
    records=db.execute(QUERY,(e,)).fetchall()
    base={};receipt={};meta=None
    for tag,n,z,d,s in records:
        if tag==0:base[n]=s
        elif tag==1:receipt[n]=s
        else:meta=(n,z,d)
    if mode=="L":assert meta is not None
    goal=base if meta is None else material(path,base,receipt,*meta)
    return tuple(sorted(goal.items())),1,len(records)
