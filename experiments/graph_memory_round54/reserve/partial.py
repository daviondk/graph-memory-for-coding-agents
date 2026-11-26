"""Exact lazy reserve that restores only the uncertified suffix. Reuse the published-comparator SQL."""
from collections import Counter
from classic import ClassicStore
from reserve_store import key
from core import M


def certify(state, dirty, capacity):
    cached,bound = state
    pool = dict(cached)
    for cid,score in dirty.items():
        if score is None:
            pool.pop(cid,None)
        else:
            pool[cid]=score
    ordered = sorted(pool.items(),key=key,reverse=True)
    if len(ordered)>capacity:
        released=key(ordered[capacity])
        bound=released if bound is None else max(released,bound)
    keep=tuple(ordered[:capacity])
    prefix=keep if bound is None else tuple(p for p in keep if key(p)>=bound)
    return keep,bound,prefix


class PartialStore(ClassicStore):
    def __init__(self,db,capacity,mode="partial",create=True):
        assert mode=="partial"
        super().__init__(db,capacity,"classic",create)
        self.mode=mode

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
            keep,bound,prefix=certify(state,dirty,self.capacity)
            if bound is not None and len(prefix)<M:
                nxt=self.refill(q,prefix)
            else:
                nxt=(keep,bound)
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

