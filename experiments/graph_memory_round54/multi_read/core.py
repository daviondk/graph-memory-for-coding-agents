"""Atomic signed source updates and exact top-M access over five physical histories."""
from collections import Counter
from pathlib import Path
import sqlite3
import sys
D=Path(__file__).resolve().parent
OLD=D.parents[1]/"graph_memory_round53/churn"
sys.path.insert(0,str(OLD))
from engine import CORE,CANDIDATES,connect
from source import sig,reads,read
M=8
PLANS=("snapshot","slots","blocks","admitted","candidate")
KS=(2,4,8)
BASE=CORE[:CORE.index("CREATE TABLE winner")]
PACK="CREATE TABLE packet(q TEXT,part INTEGER,rev INTEGER,payload BLOB NOT NULL,PRIMARY KEY(q,part,rev)) WITHOUT ROWID;"
NOW="SELECT cid,score FROM source WHERE q=? ORDER BY score DESC,cid LIMIT ?"
INTERVAL="SELECT cid,score FROM cv INDEXED BY cv_best WHERE q=? AND beg<=? AND (end IS NULL OR end>?) ORDER BY score DESC,cid LIMIT ?"
def pack(pairs):
    out=bytearray()
    for pair in pairs:
        for n in pair:
            if n<0:raise ValueError("negative packed integer")
            while n>=128:out.append((n&127)|128);n>>=7
            out.append(n)
    return bytes(out)
def unpack(b,limit):
    vals=[];n=shift=0
    for c in b:
        n|=(c&127)<<shift
        if c>=128:shift+=7;continue
        vals.append(n);n=shift=0
        if len(vals)==2*limit:break
    assert not shift and len(vals)%2==0
    return list(zip(vals[::2],vals[1::2]))
GROUPS={"snapshot":[(0,M)],"blocks":[(0,2),(2,4),(4,8)],"slots":[(i,i+1) for i in range(M)]}
def predecessor(n):
    return "SELECT "+",".join("(SELECT payload FROM packet WHERE q=?1 AND part="+str(j)+" AND rev<=?2 ORDER BY rev DESC LIMIT 1)" for j in range(n))
QUERIES={n:predecessor(n) for n in range(1,9)}
class Store:
    def __init__(self,db,plan,create=True):
        if plan not in PLANS:raise ValueError(plan)
        self.db=db;self.plan=plan;self.last={}
        if create:db.executescript(BASE+(PACK if plan in GROUPS else CANDIDATES))
    def _top(self,q,k):return self.db.execute(NOW,(q,k)).fetchall()
    def _history(self,q,t,k):
        if self.plan not in GROUPS:return self.db.execute(INTERVAL,(q,t,t,k)).fetchall()
        cnt=sum(lo<k for lo,hi in GROUPS[self.plan])
        blobs=self.db.execute(QUERIES[cnt],(q,t)).fetchone();out=[]
        for b in blobs:
            if b:out.extend(unpack(b,k-len(out)))
        return out
    def get(self,q,t,k):
        if k not in KS:raise ValueError("unsupported k")
        c=self.db;c.execute("BEGIN")
        try:
            head=c.execute("SELECT rev FROM head WHERE q=?",(q,)).fetchone();n=head[0] if head else 0
            if not 0<=t<=n:raise ValueError("uncommitted version")
            out=self._top(q,k) if n==t else self._history(q,t,k);c.commit();return out
        except BaseException:c.rollback();raise
    def _maintain(self,q,t,old,new,born,changed):
        c=self.db
        if self.plan in GROUPS:
            for j,(a,b) in enumerate(GROUPS[self.plan]):
                if old[a:b]!=new[a:b]:c.execute("INSERT INTO packet VALUES(?,?,?,?)",(q,j,t,pack(new[a:b])))
        elif self.plan=="admitted":
            left,right=dict(old),dict(new)
            for i,s in left.items():
                if right.get(i)!=s:c.execute("UPDATE cv SET end=? WHERE q=? AND cid=? AND end IS NULL",(t,q,i))
            for i,s in right.items():
                if left.get(i)!=s:c.execute("INSERT INTO cv VALUES(?,?,?,NULL,?)",(q,i,t,s))
        else:
            for i in sorted(set(born)|{i for i,v in changed.items() if v}):
                c.execute("UPDATE cv SET end=? WHERE q=? AND cid=? AND end IS NULL",(t,q,i))
                c.execute("INSERT INTO cv SELECT q,cid,?,NULL,score FROM source WHERE q=? AND cid=?",(t,q,i))
    def update(self,q,row,fault=False):
        c=self.db;t=row["t"];born=row["born"];delta=row["delta"];receipt=row["sha"]
        c.execute("BEGIN IMMEDIATE")
        try:
            head=c.execute("SELECT rev FROM head WHERE q=?",(q,)).fetchone();n=head[0] if head else 0
            if t<=n:
                if c.execute("SELECT digest FROM receipt WHERE q=? AND rev=?",(q,t)).fetchone()!=(receipt,):raise ValueError("conflicting replay")
                c.commit();return False
            if t!=n+1:raise ValueError("version gap")
            old=new=()
            if self.plan!="candidate":
                cached=self.last.get(q);old=cached[1] if cached and cached[0]==n else self._top(q,M)
            for i in born:c.execute("INSERT INTO source VALUES(?,?,?,0)",(q,i,t))
            net=Counter()
            for a,b,d in delta:
                pair=(q,a,b);prev=c.execute("SELECT weight FROM edge WHERE q=? AND src=? AND dst=? AND end IS NULL",pair).fetchone()
                w=(prev[0] if prev else 0)+d
                if d==0 or w<0 or c.execute("SELECT count(*) FROM source WHERE q=? AND cid IN (?,?)",(q,a,b)).fetchone()[0]!=len({a,b}):raise ValueError("invalid edge")
                if prev:c.execute("UPDATE edge SET end=? WHERE q=? AND src=? AND dst=? AND end IS NULL",(t,*pair))
                if w:c.execute("INSERT INTO edge VALUES(?,?,?,?,NULL,?)",(*pair,t,w))
                net[a]+=d
            for i,v in net.items():
                if v:c.execute("UPDATE source SET score=score+? WHERE q=? AND cid=?",(v,q,i))
            if self.plan!="candidate":new=self._top(q,M)
            self._maintain(q,t,old,new,born,net)
            if fault:raise RuntimeError("test rollback")
            c.execute("INSERT INTO receipt VALUES(?,?,?)",(q,t,receipt))
            c.execute("INSERT INTO head VALUES(?,?) ON CONFLICT(q) DO UPDATE SET rev=excluded.rev",(q,t))
            c.commit()
            if self.plan!="candidate":self.last[q]=(t,new)
            return True
        except BaseException:c.rollback();raise
