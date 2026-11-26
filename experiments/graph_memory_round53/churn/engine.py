"""Three physical plans over one atomic versioned relation. Each edit is a net at one revision."""
from collections import Counter
import sqlite3
from source import sig

CORE="""
CREATE TABLE head(q TEXT PRIMARY KEY,rev INTEGER NOT NULL) WITHOUT ROWID;
CREATE TABLE receipt(q TEXT,rev INTEGER,digest TEXT NOT NULL, PRIMARY KEY(q,rev)) WITHOUT ROWID;
CREATE TABLE source(q TEXT,cid INTEGER,birth INTEGER NOT NULL,score INTEGER NOT NULL CHECK(score>=0),
                    PRIMARY KEY(q,cid)) WITHOUT ROWID;
CREATE INDEX source_best ON source(q,score DESC,cid);
CREATE TABLE edge(q TEXT,src INTEGER,dst INTEGER,beg INTEGER,end INTEGER,weight INTEGER NOT NULL CHECK(weight>0),
                  PRIMARY KEY(q,src,dst,beg),CHECK(end IS NULL OR end>beg)) WITHOUT ROWID;
CREATE UNIQUE INDEX edge_open ON edge(q,src,dst) WHERE end IS NULL;
CREATE TABLE winner(q TEXT,rev INTEGER,cid INTEGER NOT NULL,score INTEGER NOT NULL,PRIMARY KEY(q,rev)) WITHOUT ROWID;
"""
CANDIDATES="""
CREATE TABLE cv(q TEXT,cid INTEGER,beg INTEGER,end INTEGER,score INTEGER NOT NULL,
                PRIMARY KEY(q,cid,beg),CHECK(end IS NULL OR end>beg)) WITHOUT ROWID;
CREATE UNIQUE INDEX cv_open ON cv(q,cid) WHERE end IS NULL;
CREATE INDEX cv_best ON cv(q,score DESC,cid,beg,end);
"""
CURRENT="SELECT cid,score FROM source WHERE q=? ORDER BY score DESC,cid LIMIT 1"
PREV="SELECT cid,score FROM winner WHERE q=? AND rev<=? ORDER BY rev DESC LIMIT 1"
VER="SELECT cid,score FROM cv INDEXED BY cv_best WHERE q=? AND beg<=? AND (end IS NULL OR end>?) ORDER BY score DESC,cid LIMIT 1"
RAW="""SELECT s.cid,COALESCE(SUM(e.weight),0) v FROM source s LEFT JOIN edge e
ON e.q=s.q AND e.src=s.cid AND e.beg<=? AND (e.end IS NULL OR e.end>?)
WHERE s.q=? AND s.birth<=? GROUP BY s.cid ORDER BY v DESC,s.cid LIMIT 1"""
def connect(path):
    c=sqlite3.connect(path,isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL");c.execute("PRAGMA synchronous=NORMAL");c.execute("PRAGMA wal_autocheckpoint=0")
    return c
class Engine:
    def __init__(self,db,plan,*,create=False):
        if plan not in ("interval","candidate","journal"):raise ValueError(plan)
        self.db,self.plan=db,plan
        if create:db.executescript(CORE+(CANDIDATES if plan=="candidate" else ""))
    def current(self,q):return self.db.execute(CURRENT,(q,)).fetchone()
    def history(self,q,t):
        if self.plan=="journal":return self.db.execute(PREV,(q,t)).fetchone()
        if self.plan=="candidate":return self.db.execute(VER,(q,t,t)).fetchone()
        return self.db.execute(RAW,(t,t,q,t)).fetchone()
    def get(self,q,t):
        # Pin version and selected value to the same snapshot in the presence of concurrent writers.
        owned=not self.db.in_transaction
        if owned:self.db.execute("BEGIN")
        try:
            head=self.db.execute("SELECT rev FROM head WHERE q=?",(q,)).fetchone()
            now=head[0] if head else 0
            if not 0<=t<=now:raise ValueError("revision outside committed timeline")
            result=self.current(q) if t==now else self.history(q,t)
            if owned:self.db.commit()
            return result
        except BaseException:
            if owned:self.db.rollback()
            raise
    def update(self,q,t,born,delta,receipt,*,fail_after_edges=False):
        # Cost of calculating the canonical caller receipt is outside benchmark timing.
        c=self.db;c.execute("BEGIN IMMEDIATE")
        try:
            old=c.execute("SELECT rev FROM head WHERE q=?",(q,)).fetchone()
            now=old[0] if old else 0
            if t<=now:
                r=c.execute("SELECT digest FROM receipt WHERE q=? AND rev=?",(q,t)).fetchone()
                if r!=(receipt,):raise ValueError("different payload at existing revision")
                c.commit();return False
            if t!=now+1:raise ValueError("non-consecutive revision")
            if len(set(born))!=len(born):raise ValueError("duplicate birth")
            touched=Counter()
            for i in born:c.execute("INSERT INTO source VALUES(?,?,?,0)",(q,i,t))
            for a,b,d in delta:
                # Caller has normalized same-step operations, allowing only one net per edge.
                pair=(q,a,b)
                was=c.execute("SELECT weight FROM edge WHERE q=? AND src=? AND dst=? AND end IS NULL",pair).fetchone()
                w=(was[0] if was else 0)+d
                if not d or w<0:raise ValueError("invalid net edge update")
                if c.execute("SELECT count(*) FROM source WHERE q=? AND cid IN (?,?)",(q,a,b)).fetchone()[0]!=len({a,b}):
                    raise ValueError("unknown edge endpoint")
                if was:c.execute("UPDATE edge SET end=? WHERE q=? AND src=? AND dst=? AND end IS NULL",(t,*pair))
                if w:c.execute("INSERT INTO edge VALUES(?,?,?,?,NULL,?)",(*pair,t,w))
                touched[a]+=d
            if fail_after_edges:raise RuntimeError("injected failure after interval edits")
            for i,amount in touched.items():
                if amount:c.execute("UPDATE source SET score=score+? WHERE q=? AND cid=?",(amount,q,i))
            if self.plan=="candidate":
                for i in set(born)|{i for i,n in touched.items() if n}:
                    c.execute("UPDATE cv SET end=? WHERE q=? AND cid=? AND end IS NULL",(t,q,i))
                    c.execute("INSERT INTO cv SELECT q,cid,?,NULL,score FROM source WHERE q=? AND cid=?",(t,q,i))
            if self.plan=="journal":
                best=self.current(q)
                if best is not None and best!=c.execute(PREV,(q,now)).fetchone():
                    c.execute("INSERT INTO winner VALUES(?,?,?,?)",(q,t,*best))
            c.execute("INSERT INTO receipt VALUES(?,?,?)",(q,t,receipt))
            c.execute("INSERT INTO head VALUES(?,?) ON CONFLICT(q) DO UPDATE SET rev=excluded.rev",(q,t))
            c.commit();return True
        except BaseException:
            c.rollback();raise
    def apply(self,q,t,born,changes,fail_after_edges=False):
        net=Counter()
        for a,b,d in changes:net[a,b]+=d
        delta=sorted([a,b,n] for (a,b),n in net.items() if n)
        return self.update(q,t,sorted(born),delta,sig(born,delta),fail_after_edges=fail_after_edges)

