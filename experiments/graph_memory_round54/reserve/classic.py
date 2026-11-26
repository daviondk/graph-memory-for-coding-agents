"""Exact variable prefix and partial index refill after underflow, adapted from Yi et al. (ICDE 2003)."""
from collections import Counter
from reserve_store import ReserveStore, key, refresh
from core import M, NOW

SUFFIX = """SELECT cid,score FROM source WHERE q=? AND score<=? AND (score<? OR cid>?)
            ORDER BY score DESC,cid LIMIT ?"""


def prefix_step(state,dirty,capacity):
    """Produce a guaranteed exact (possibly short) prefix after an atomic update."""
    known, outside = state
    pool = dict(known)
    for cid,score in dirty.items():
        if score is None:
            pool.pop(cid,None)
        else:
            pool[cid]=score
    floor = key(known[-1]) if outside is not None else None
    eligible = sorted((pair for pair in pool.items() if floor is None or key(pair)>=floor),
                      key=key,reverse=True)
    complete = outside is None and len(eligible)<=capacity
    return tuple(eligible[:capacity]),complete


class ClassicStore(ReserveStore):
    def __init__(self,db,capacity,mode="classic",create=True):
        assert mode=="classic"
        super().__init__(db,capacity,"lazy",create)
        self.mode="classic"

    def refill(self,q,prefix):
        free=self.capacity-len(prefix)
        if prefix:
            cid,score=prefix[-1]
            extra=self.db.execute(SUFFIX,(q,score,score,cid,free)).fetchall()
        else:
            extra=self.db.execute(NOW,(q,free)).fetchall()
        self.event["warm_probes"]+=1
        self.event["warm_rows"]+=len(extra)
        return refresh(prefix+tuple(extra),self.capacity)

    def update(self,q,row,fault=False):
        c=self.db
        t=row["t"]
        self.event=Counter()
        c.execute("BEGIN IMMEDIATE")
        try:
            head=c.execute("SELECT rev FROM head WHERE q=?",(q,)).fetchone()
            rev=head[0] if head else 0
            if t<=rev:
                if c.execute("SELECT digest FROM receipt WHERE q=? AND rev=?",(q,t)).fetchone()!=(row["sha"],):
                    raise ValueError("conflicting replay")
                c.commit()
                return False
            if t!=rev+1:
                raise ValueError("version gap")
            prior=self.last.get(q)
            state=prior[1] if prior and prior[0]==rev else self.fetch(q,"cold")
            old=list(state[0][:M])
            dirty=dict.fromkeys(row["born"],0)
            for cid in row["born"]:
                c.execute("INSERT INTO source VALUES(?,?,?,0)",(q,cid,t))
            net=Counter()
            for a,b,d in row["delta"]:
                endpoints=(q,a,b)
                prev=c.execute("SELECT weight FROM edge WHERE q=? AND src=? AND dst=? AND end IS NULL",endpoints).fetchone()
                new=(prev[0] if prev else 0)+d
                count=c.execute("SELECT count(*) FROM source WHERE q=? AND cid IN (?,?)",(q,a,b)).fetchone()[0]
                if not d or new<0 or count!=len({a,b}):
                    raise ValueError("invalid edge")
                if prev:
                    c.execute("UPDATE edge SET end=? WHERE q=? AND src=? AND dst=? AND end IS NULL",(t,*endpoints))
                if new:
                    c.execute("INSERT INTO edge VALUES(?,?,?,?,NULL,?)",(*endpoints,t,new))
                net[a]+=d
            for cid,v in net.items():
                if v:
                    dirty[cid]=c.execute("UPDATE source SET score=score+? WHERE q=? AND cid=? RETURNING score",(v,q,cid)).fetchone()[0]
                    self.event["score_rows"]+=1
            prefix,complete=prefix_step(state,dirty,self.capacity)
            if not complete and len(prefix)<M:
                nxt=self.refill(q,prefix)
            else:
                nxt=(prefix,None if complete else key(prefix[-1]))
            packet=list(nxt[0][:M])
            self._maintain(q,t,old,packet,row["born"],net)
            if fault:
                raise RuntimeError("test rollback")
            c.execute("INSERT INTO receipt VALUES(?,?,?)",(q,t,row["sha"]))
            c.execute("INSERT INTO head VALUES(?,?) ON CONFLICT(q) DO UPDATE SET rev=excluded.rev",(q,t))
            c.commit()
            self.last[q]=(t,nxt)
            self.event["pairs"]=len(nxt[0])
            self.event["has_bound"]=int(nxt[1] is not None)
            return True
        except BaseException:
            c.rollback()
            raise

