"""Four disk-backed SQLite implementations of apply-group and read-all-flags."""
import sqlite3

ARMS=('pair','ends','sql_group','co','scan')
PAIR_SCHEMA="""
CREATE TABLE pair(t INTEGER,a INTEGER,b INTEGER,w INTEGER NOT NULL,
    PRIMARY KEY(t,a,b)) WITHOUT ROWID;
CREATE INDEX pair_in ON pair(t,b,a);
"""
END_SCHEMA="""
CREATE TABLE endpoint(t INTEGER,v INTEGER,nout INTEGER NOT NULL,nin INTEGER NOT NULL,
    PRIMARY KEY(t,v)) WITHOUT ROWID;
"""
PAIR_READ="""
SELECT a,1 FROM (SELECT DISTINCT a FROM pair WHERE t=?)
UNION ALL SELECT b,2 FROM (SELECT DISTINCT b FROM pair INDEXED BY pair_in WHERE t=?)
"""
SCAN_READ="SELECT a,b FROM pair WHERE t=?"
END_READ="SELECT v,(nout>0) | ((nin>0)<<1) FROM endpoint WHERE t=?"
PAIR_PUT="""
INSERT INTO pair VALUES(?,?,?,?) ON CONFLICT(t,a,b) DO UPDATE SET w=pair.w+excluded.w
"""
END_PUT="""
INSERT INTO endpoint VALUES(?,?,?,?) ON CONFLICT(t,v) DO UPDATE SET
nout=endpoint.nout+excluded.nout,nin=endpoint.nin+excluded.nin
"""
SQL_GROUP="""
INSERT INTO endpoint(t,v,nout,nin)
SELECT ?,v,sum(outs),sum(ins) FROM (
    SELECT a AS v,s AS outs,0 AS ins FROM delta
    UNION ALL SELECT b AS v,0 AS outs,s AS ins FROM delta
) GROUP BY v HAVING sum(outs)<>0 OR sum(ins)<>0
ON CONFLICT(t,v) DO UPDATE SET nout=endpoint.nout+excluded.nout,nin=endpoint.nin+excluded.nin
"""

def connect(path,arm,create):
    db=sqlite3.connect(path,isolation_level=None)
    if create:db.execute('PRAGMA page_size=4096')
    assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
    for pragma in ('synchronous=NORMAL','cache_size=-16384','wal_autocheckpoint=0','temp_store=MEMORY','mmap_size=0'):
        db.execute('PRAGMA '+pragma)
    if create and arm in ('pair','co','scan'):db.executescript(PAIR_SCHEMA)
    if create and arm not in ('pair','scan'):db.executescript(END_SCHEMA)
    if arm=='sql_group':db.execute('CREATE TEMP TABLE delta(a INTEGER,b INTEGER,s INTEGER)')
    return db

def pair_update(db,t,batch):
    net={}
    for a,b,s in batch:net[a,b]=net.get((a,b),0)+s
    rows=[(t,a,b,w) for (a,b),w in net.items() if w]
    db.executemany(PAIR_PUT,rows)
    db.executemany('DELETE FROM pair WHERE t=? AND a=? AND b=? AND w=0',
                   ((t,a,b) for _,a,b,w in rows if w<0))

def end_update(db,t,batch):
    net={}
    for a,b,s in batch:
        if a not in net:net[a]=[0,0]
        if b not in net:net[b]=[0,0]
        net[a][0]+=s;net[b][1]+=s
    rows=[(t,v,x,y) for v,(x,y) in net.items() if x or y]
    db.executemany(END_PUT,rows)
    db.executemany('DELETE FROM endpoint WHERE t=? AND v=? AND nout=0 AND nin=0',
                   ((t,v) for _,v,x,y in rows if x<0 or y<0))

def apply(db,arm,t,batch):
    db.execute('BEGIN')
    if batch:
        if arm in ('pair','co','scan'):pair_update(db,t,batch)
        if arm in ('ends','co'):end_update(db,t,batch)
        elif arm=='sql_group':
            db.executemany('INSERT INTO delta VALUES(?,?,?)',batch)
            db.execute(SQL_GROUP,(t,))
            db.execute('DELETE FROM endpoint WHERE t=? AND nout=0 AND nin=0',(t,))
            db.execute('DELETE FROM delta')
    db.execute('COMMIT')

def flags(db,arm,t):
    if arm=='scan':
        out={}
        for a,b in db.execute(SCAN_READ,(t,)):
            out[a]=out.get(a,0)|1;out[b]=out.get(b,0)|2
        return out
    if arm=='pair':
        out={}
        for v,bit in db.execute(PAIR_READ,(t,t)):out[v]=out.get(v,0)|bit
        return out
    return dict(db.execute(END_READ,(t,)))
