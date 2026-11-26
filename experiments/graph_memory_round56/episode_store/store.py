"""SQLite catalogs and incidence views. All persistent state needed for reads is in the DB."""
from collections import Counter
import sqlite3
import extra_store
import sweep_store
from codec import blob_ids, ids_blob, bounded_update, profile, unpack_events, record

SCHEMAS = {
    'pairs': "CREATE TABLE pair(a INTEGER,b INTEGER,n INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;",
    'log': """CREATE TABLE episode(id INTEGER PRIMARY KEY,v BLOB NOT NULL);
              CREATE TABLE incident(a INTEGER,t INTEGER,PRIMARY KEY(a,t)) WITHOUT ROWID;""",
    'shared': """CREATE TABLE episode(id INTEGER PRIMARY KEY,v BLOB NOT NULL,n INTEGER NOT NULL);
                 CREATE TABLE incident(a INTEGER,t INTEGER,PRIMARY KEY(a,t)) WITHOUT ROWID;""",
    'intern': """CREATE TABLE episode(id INTEGER PRIMARY KEY,v BLOB UNIQUE NOT NULL,n INTEGER NOT NULL);
                 CREATE TABLE incident(a INTEGER,t INTEGER,h INTEGER NOT NULL,PRIMARY KEY(a,t)) WITHOUT ROWID;""",
    'inline': "CREATE TABLE packet(a INTEGER PRIMARY KEY,v BLOB NOT NULL);",
    'fixed': "CREATE TABLE packet(a INTEGER PRIMARY KEY,v BLOB NOT NULL);",
}
LAYOUTS = ('pairs','log','inline','shared','intern')
FIXED = ('raw','skip','runs','space','lossy')

def connect(path):
    db=sqlite3.connect(path, isolation_level=None)
    db.execute("PRAGMA journal_mode=MEMORY")
    db.execute("PRAGMA synchronous=OFF")
    db.execute("PRAGMA mmap_size=0")
    db.execute("PRAGMA cache_size=-1024")
    return db

def initialize(db,mode):
    db.executescript("""PRAGMA page_size=4096;
        CREATE TABLE node(id INTEGER PRIMARY KEY,path TEXT NOT NULL UNIQUE,f INTEGER NOT NULL);
        CREATE TABLE window(t INTEGER PRIMARY KEY,v BLOB NOT NULL);""")
    if mode in sweep_store.MODES:
        db.executescript(sweep_store.DDL[mode])
    elif mode in extra_store.EXTRA:
        db.executescript(extra_store.SCHEMA[mode])
    else:
        db.executescript(SCHEMAS[mode if mode in LAYOUTS else 'fixed'])

def update(db,mode,budget,t,nodes,born):
    """One atomic first-parent transition. IDs are sequential in order of discovery."""
    db.execute('BEGIN IMMEDIATE')
    try:
        db.executemany("INSERT INTO node VALUES(?,?,0)",born)
        if mode in FIXED:
            db.executemany("INSERT INTO packet VALUES(?,zeroblob(?))",[(i,budget) for i,_ in born])
        payload=ids_blob(nodes)
        if t>=32:
            old,=db.execute("SELECT v FROM window WHERE t=?",(t-32,)).fetchone()
            db.executemany("UPDATE node SET f=f-1 WHERE id=?",[(i,) for i in blob_ids(old)])
            db.execute("DELETE FROM window WHERE t=?",(t-32,))
        db.execute("INSERT INTO window VALUES(?,?)",(t,payload))
        db.executemany("UPDATE node SET f=f+1 WHERE id=?",[(i,) for i in nodes])
        if nodes:
            write_view(db,mode,budget,t,nodes,payload)
        if mode in ('sweepscan','blocksweep') and (t+1)%sweep_store.BLOCK==0:
            sweep_store.sweep(db,mode)
        db.commit()
    except BaseException:
        db.rollback()
        raise

def write_view(db,mode,budget,t,nodes,payload):
    if mode in sweep_store.MODES:
        return sweep_store.add(db,mode,t,nodes,payload)
    if mode in extra_store.EXTRA:
        return extra_store.write(db,mode,t,nodes,payload)
    if mode=='pairs':
        db.executemany("""INSERT INTO pair VALUES(?,?,1) ON CONFLICT(a,b)
                          DO UPDATE SET n=n+1""",((a,b) for a in nodes for b in nodes if a!=b))
    elif mode=='inline':
        for a in nodes:
            old=db.execute("SELECT v FROM packet WHERE a=?",(a,)).fetchone()
            # Positive count field doubles as the source revision + 1.
            history=unpack_events(old[0])[:7] if old else []
            joined=record(t+1,payload)+b''.join(record(n,v) for n,v in history)
            db.execute("INSERT OR REPLACE INTO packet VALUES(?,?)",(a,joined))
    elif mode in ('log','shared','intern'):
        if mode=='log':
            db.execute("INSERT INTO episode VALUES(?,?)",(t,payload))
        elif mode=='shared':
            db.execute("INSERT INTO episode VALUES(?,?,?)",(t,payload,len(nodes)))
        else:
            h,=db.execute("""INSERT INTO episode(v,n) VALUES(?,?) ON CONFLICT(v)
                            DO UPDATE SET n=n+excluded.n RETURNING id""",(payload,len(nodes))).fetchone()
        if mode=='intern':
            db.executemany("INSERT INTO incident VALUES(?,?,?)",[(a,t,h) for a in nodes])
        else:
            db.executemany("INSERT INTO incident VALUES(?,?)",[(a,t) for a in nodes])
        if mode!='log':
            for a in nodes:
                sql='SELECT t,h' if mode=='intern' else 'SELECT t,t'
                dead=db.execute(sql+" FROM incident WHERE a=? ORDER BY t DESC LIMIT 1 OFFSET 8",(a,)).fetchone()
                if dead:
                    old_t,old_h=dead
                    db.execute("DELETE FROM incident WHERE a=? AND t=?",(a,old_t))
                    remaining,=db.execute("UPDATE episode SET n=n-1 WHERE id=? RETURNING n",(old_h,)).fetchone()
                    if remaining==0:
                        db.execute("DELETE FROM episode WHERE id=?",(old_h,))
    else:
        for a in nodes:
            old,=db.execute("SELECT v FROM packet WHERE a=?",(a,)).fetchone()
            nxt=bounded_update(mode,old,tuple(i for i in nodes if i!=a),budget)
            if nxt!=old:
                db.execute("UPDATE packet SET v=? WHERE a=?",(nxt,a))

def evidence(db,mode,a):
    if mode in sweep_store.MODES:
        return sweep_store.evidence(db,mode,a)
    if mode in extra_store.EXTRA:
        return extra_store.evidence(db,mode,a)
    if mode=='pairs':
        return dict(db.execute("SELECT b,n FROM pair WHERE a=?",(a,)))
    if mode=='inline' or mode in FIXED:
        row=db.execute("SELECT v FROM packet WHERE a=?",(a,)).fetchone()
        if not row:return {}
        if mode in FIXED:return profile(mode,row[0])
        items=[v for _,v in unpack_events(row[0])]
    else:
        col='h' if mode=='intern' else 't'
        items=(v for v, in db.execute("SELECT e.v FROM incident i JOIN episode e ON e.id=i."+col+
                                      " WHERE i.a=?",(a,)))
    counts=Counter(i for data in items for i in blob_ids(data))
    counts.pop(a,None)
    return counts

def top(db,mode,a):
    scores=evidence(db,mode,a)
    # Full common tie-break uses the last 32 revisions; a fresh reader needs no prior Python cache.
    ids=db.execute("SELECT id,f FROM node WHERE id!=?",(a,)).fetchall()
    return tuple(i for i,f in sorted(ids,key=lambda p:(-scores.get(p[0],0),-p[1],p[0]))[:8])

def state(db,mode):
    if mode in sweep_store.MODES:
        return sweep_store.tables(db,mode)
    if mode in extra_store.EXTRA:
        return extra_store.tables(db,mode)
    tables=['node','window']
    tables+=['pair'] if mode=='pairs' else ['episode','incident'] if mode in ('log','shared','intern') else ['packet']
    rows={tab:db.execute("SELECT COUNT(*) FROM "+tab).fetchone()[0] for tab in tables}
    if mode in ('shared','intern'):
        col='h' if mode=='intern' else 't'
        mismatch=db.execute("SELECT e.id,e.n,COUNT(i.a) FROM episode e LEFT JOIN incident i ON i."+
                            col+"=e.id GROUP BY e.id HAVING e.n!=COUNT(i.a) OR e.n<1").fetchall()
        assert not mismatch
        assert rows['incident']==db.execute('SELECT COALESCE(SUM(n),0) FROM episode').fetchone()[0]
        assert not db.execute("SELECT a FROM incident GROUP BY a HAVING COUNT(*)>8").fetchone()
    return rows
