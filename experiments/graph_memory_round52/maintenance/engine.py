"""Physical plans for as-of top-one lookup with monotonically certified graph edges."""
from pathlib import Path
import sqlite3

PLANS=("scan","cover","partial","eligible","journal")
BASE_SCHEMA="""
CREATE TABLE cursor(q INTEGER PRIMARY KEY, upto INTEGER NOT NULL DEFAULT 0);
CREATE TABLE c(q INT NOT NULL,id INT NOT NULL,r INT NOT NULL,b REAL NOT NULL,u REAL NOT NULL,
               seen INT, PRIMARY KEY(q,id)) WITHOUT ROWID;
"""
ACTIVE="CASE WHEN seen IS NOT NULL THEN u ELSE b END"
ASOF="CASE WHEN seen<=?2 THEN u ELSE b END"
ANCHOR="""
CREATE TABLE anchor(q INTEGER PRIMARY KEY, id INT NOT NULL, r INT NOT NULL,b REAL NOT NULL);
INSERT INTO anchor SELECT q,id,r,b FROM
 (SELECT q,id,r,b, ROW_NUMBER() OVER (PARTITION BY q ORDER BY b DESC,r,id) AS k FROM c)
 WHERE k=1;
"""
JOURNAL="""
CREATE TABLE history(q INT, step INT, id INT NOT NULL, score REAL NOT NULL,r INT NOT NULL,
                     PRIMARY KEY(q,step)) WITHOUT ROWID;
INSERT INTO history SELECT q,0,id,b,r FROM
  (SELECT q,id,b,r,ROW_NUMBER() OVER (PARTITION BY q ORDER BY b DESC,r,id) AS k FROM c)
  WHERE k=1;
CREATE TRIGGER promote AFTER UPDATE OF seen ON c WHEN OLD.seen IS NULL AND NEW.seen IS NOT NULL BEGIN
  INSERT OR REPLACE INTO history
  SELECT NEW.q,NEW.seen,NEW.id,NEW.u,NEW.r
  FROM (SELECT score,r,id FROM history WHERE q=NEW.q ORDER BY step DESC LIMIT 1)
  WHERE NEW.u>score OR (NEW.u=score AND (NEW.r,NEW.id)<(r,id));
END;
"""
def connect(path):
    db=sqlite3.connect(path,isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("PRAGMA cache_size=-24576")
    db.execute("PRAGMA temp_store=MEMORY")
    return db

def setup(db,plan):
    if plan=="scan":
        return
    if plan=="journal":
        ddl=JOURNAL
    elif plan=="cover":
        ddl="CREATE INDEX leaders ON c(q,("+ACTIVE+") DESC,r,id);"
    else:
        ddl=ANCHOR
        if plan=="eligible":
            ddl+="""
            ALTER TABLE c ADD COLUMN ok INT NOT NULL DEFAULT 0;
            UPDATE c SET ok=1 FROM anchor a WHERE c.q=a.q AND
              (c.u>a.b OR (c.u=a.b AND (c.r,c.id)<=(a.r,a.id)));
            """
        where="seen IS NOT NULL"+(" AND ok=1" if plan=="eligible" else "")
        ddl+=f"CREATE INDEX marked ON c(q,u DESC,r,id,seen) WHERE {where};"
    db.executescript("BEGIN;"+ddl+"COMMIT;")

def statement(plan,live):
    if plan=="journal":
        return "SELECT id FROM history WHERE q=?1 AND step<=?2 ORDER BY step DESC LIMIT 1"
    if plan=="cover" and live:
        return f"SELECT id FROM c INDEXED BY leaders WHERE q=?1 AND ?2>=0 ORDER BY ({ACTIVE}) DESC,r,id LIMIT 1"
    if plan in ("scan","cover"):
        return f"SELECT id FROM c NOT INDEXED WHERE q=?1 ORDER BY ({ASOF}) DESC,r,id LIMIT 1"
    if plan=="eligible":
        where="c.ok=1"
    else:
        where="(u>a.b OR (u=a.b AND (c.r,c.id)<=(a.r,a.id)))"
    return f"""SELECT coalesce((SELECT id FROM c INDEXED BY marked WHERE c.q=a.q AND seen IS NOT NULL
            AND seen<=?2 AND {where} ORDER BY u DESC,r,id LIMIT 1),a.id)
            FROM anchor a WHERE a.q=?1"""

def advance(db,q,step,ids):
    db.execute("BEGIN IMMEDIATE")
    try:
        if ids:
            db.executemany("UPDATE c SET seen=? WHERE q=? AND id=? AND seen IS NULL",[(step,q,i) for i in ids])
        db.execute("UPDATE cursor SET upto=max(upto,?) WHERE q=?",(step,q))
        db.commit()
    except BaseException:
        db.rollback()
        raise

def create_base(path,rows):
    with connect(path) as db:
        db.executescript(BASE_SCHEMA)
        db.execute("BEGIN")
        for q,episode in rows:
            db.execute("INSERT INTO cursor(q) VALUES(?)",(q,))
            db.executemany("INSERT INTO c VALUES(?,?,?,?,?,NULL)",[(q,i,r,b,u) for i,r,b,u,step in episode["candidates"]])
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.close()

