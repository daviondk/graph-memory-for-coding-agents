"""Maintain exact ranked evidence packets against an ordered SQLite index."""
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"multi_read"))
from core import M, Store

PLANS = ("index", "unchanged", "boundary")

def local_top(old, updates, k, mode):
    """Return exact candidates, or None when an unseen predecessor can outrank the result."""
    if not updates:
        return old, "reuse"
    if len(old) == k:
        incumbent = dict(old)
        score, neg_id = old[-1][1], -old[-1][0]
        if all((i not in incumbent and (v, -i) < (score, neg_id))
               or incumbent.get(i) == v for i,v in updates.items()):
            return old, "reuse"
    if mode == "unchanged":
        return None, "index"
    pool = dict(old)
    pool.update(updates)
    top = sorted(pool.items(), key=lambda pair: (-pair[1], pair[0]))[:k]
    if len(old) < k or (top[-1][1], -top[-1][0]) >= (old[-1][1], -old[-1][0]):
        return top, "local"
    return None, "index"

class CutoffStore(Store):
    def __init__(self, db, mode, create=True):
        super().__init__(db, "snapshot", create)
        if mode not in PLANS:
            raise ValueError(mode)
        self.mode=mode
        self.stats=Counter()

    def update(self,q,row,fault=False):
        c=self.db
        version=row["t"]
        c.execute("BEGIN IMMEDIATE")
        try:
            head=c.execute("SELECT rev FROM head WHERE q=?", (q,)).fetchone()
            n=head[0] if head else 0
            if version<=n:
                prior=c.execute("SELECT digest FROM receipt WHERE q=? AND rev=?",(q,version)).fetchone()
                if prior!=(row["sha"],):raise ValueError("conflicting replay")
                c.commit()
                return False
            if version!=n+1:raise ValueError("version gap")
            cache=self.last.get(q)
            if cache and cache[0]==n:
                old=cache[1]
            else:
                old=self._top(q,M)
                self.stats["cold_top_selects"]+=1
            dirty={}
            for source in row["born"]:
                c.execute("INSERT INTO source VALUES(?,?,?,0)", (q,source,version))
                if self.mode!="index":dirty[source]=0
            net=Counter()
            for a,b,d in row["delta"]:
                pair=(q,a,b)
                prev=c.execute("SELECT weight FROM edge WHERE q=? AND src=? AND dst=? AND end IS NULL",pair).fetchone()
                new=(prev[0] if prev else 0)+d
                eligible=c.execute("SELECT count(*) FROM source WHERE q=? AND cid IN (?,?)",(q,a,b)).fetchone()[0]
                if d==0 or new<0 or eligible!=len({a,b}):
                    raise ValueError("invalid edge")
                if prev:c.execute("UPDATE edge SET end=? WHERE q=? AND src=? AND dst=? AND end IS NULL",(version,*pair))
                if new:c.execute("INSERT INTO edge VALUES(?,?,?,?,NULL,?)",(*pair,version,new))
                net[a]+=d
            for i,delta in net.items():
                if not delta:continue
                sql="UPDATE source SET score=score+? WHERE q=? AND cid=?"
                values=(delta,q,i)
                if self.mode=="index":c.execute(sql,values)
                else:
                    dirty[i]=c.execute(sql+" RETURNING score",values).fetchone()[0]
            if self.mode=="index":packet,how=None,"index"
            else:packet,how=local_top(old,dirty,M,self.mode)
            if packet is None:packet=self._top(q,M)
            self._maintain(q,version,old,packet,row["born"],net)
            if fault:raise RuntimeError("test rollback")
            c.execute("INSERT INTO receipt VALUES(?,?,?)",(q,version,row["sha"]))
            c.execute("INSERT INTO head VALUES(?,?) ON CONFLICT(q) DO UPDATE SET rev=excluded.rev",(q,version))
            c.commit()
            self.last[q]=(version,packet)
            self.stats[how]+=1
            if packet!=old:self.stats["changed_"+how]+=1
            return True
        except BaseException:
            c.rollback()
            raise
