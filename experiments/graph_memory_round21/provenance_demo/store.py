"""A read-only as-of interface to the SQLite evidence provenance snapshot."""
import sqlite3
from pathlib import Path

DATA = Path(__file__).with_name("provenance.sqlite")
SCHEMA = """
CREATE TABLE trace(t TEXT PRIMARY KEY, steps INTEGER NOT NULL) WITHOUT ROWID;
CREATE TABLE event(t TEXT NOT NULL, step INTEGER NOT NULL, kind TEXT NOT NULL, call INTEGER,
                   PRIMARY KEY(t,step)) WITHOUT ROWID;
CREATE TABLE endpoint(t TEXT NOT NULL, call INTEGER NOT NULL, called INTEGER NOT NULL, returned INTEGER NOT NULL,
                      PRIMARY KEY(t,call)) WITHOUT ROWID;
CREATE TABLE witness(t TEXT NOT NULL, a INTEGER NOT NULL, b INTEGER NOT NULL,
                     lo INTEGER NOT NULL, hi INTEGER, count INTEGER NOT NULL CHECK(count>0),
                     PRIMARY KEY(t,a,b,lo)) WITHOUT ROWID;
CREATE TABLE reason(t TEXT NOT NULL,a INTEGER NOT NULL,b INTEGER NOT NULL,step INTEGER NOT NULL,
                    value_id INTEGER NOT NULL, cause TEXT NOT NULL, other INTEGER,
                    PRIMARY KEY(t,a,b,step,value_id,cause)) WITHOUT ROWID;
CREATE TABLE checkpoint(t TEXT NOT NULL, step INTEGER NOT NULL, final INTEGER NOT NULL,
                        gold INTEGER NOT NULL, PRIMARY KEY(t,step)) WITHOUT ROWID;
"""
NOW="""SELECT a,b,count FROM witness WHERE t=? AND lo<=? AND (hi IS NULL OR hi>?) ORDER BY a,b"""
EVER="""SELECT a,b,1 FROM witness WHERE t=? AND lo<=? GROUP BY a,b ORDER BY a,b"""
FINAL="""SELECT w.a,w.b,w.count FROM witness w JOIN endpoint s ON s.t=w.t AND s.call=w.a
JOIN endpoint d ON d.t=w.t AND d.call=w.b
WHERE w.t=? AND w.hi IS NULL AND s.returned<=? AND d.called<=? ORDER BY w.a,w.b"""


def connect(path=DATA):
    db = sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    db.execute("PRAGMA query_only=ON")
    return db


def timeline(db,t):
    rows=db.execute("SELECT step,final,gold FROM checkpoint WHERE t=? ORDER BY step",(t,))
    return [dict(step=s,final=bool(f),gold=g) for s,f,g in rows]


def view(db,t,step):
    case=db.execute("SELECT steps FROM trace WHERE t=?",(t,)).fetchone()
    if case is None or not 0<=step<case[0]:
        raise ValueError("unknown history or event")
    kind,call=db.execute("SELECT kind,call FROM event WHERE t=? AND step=?",(t,step)).fetchone()
    args=(t,step,step)
    current={(a,b):n for a,b,n in db.execute(NOW,args)}
    historical={(a,b) for a,b,_ in db.execute(EVER,args[:2])}
    final={(a,b) for a,b,_ in db.execute(FINAL,args)}
    pairs=sorted(historical|final)
    assert set(current)<=historical
    return dict(t=t,step=step,steps=case[0],kind=kind,call=call,
        edges=[dict(a=a,b=b,witnesses=current.get((a,b),0),exact=(a,b) in current,
                    append=(a,b) in historical,final=(a,b) in final) for a,b in pairs],
        checkpoints=timeline(db,t))


def revisions(db,t,a,b,step):
    rows=db.execute("SELECT lo,hi,count FROM witness WHERE t=? AND a=? AND b=? AND lo<=? ORDER BY lo",(t,a,b,step))
    intervals=[dict(start=lo,end=hi if hi is not None and hi<=step else None,count=n) for lo,hi,n in rows]
    why=db.execute("SELECT step,value_id,cause,other FROM reason WHERE t=? AND a=? AND b=? AND step<=? ORDER BY step,value_id",(t,a,b,step))
    return {"windows":intervals,"evidence":[dict(step=j,value=v,cause=c,other=o) for j,v,c,o in why]}
