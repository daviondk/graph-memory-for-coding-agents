"""Single-writer chronological store, with an independently recoverable shared hot tier."""
from collections import Counter,defaultdict
from heapq import nlargest
from pathlib import Path
import sqlite3
import struct
from time import perf_counter_ns

SCHEMA="CREATE TABLE event(j INTEGER PRIMARY KEY,rev TEXT NOT NULL,members BLOB NOT NULL)"
POST="CREATE TABLE post(f INTEGER,j INTEGER,PRIMARY KEY(f,j)) WITHOUT ROWID"
READ="SELECT e.members FROM post p JOIN event e ON e.j=p.j WHERE p.f=?"
B=8

def encode(ids):
    return struct.pack("<"+"I"*len(ids),*ids)
def decode(blob):
    return struct.unpack("<"+"I"*(len(blob)//4),blob)
def best(values,anchor,tie,prior):
    selected=nlargest(8,((n,tie[i],-i) for i,n in values.items() if i!=anchor and n))
    result=[(-i,n) for n,_,i in selected]
    seen={i for i,_ in result}
    for i in prior:
        if len(result)>=8:break
        if i!=anchor and i not in seen:result.append((i,0))
    return result

class Store:
    def __init__(self,path,mode,create=False):
        if mode not in {"full","own","split"}:raise ValueError(mode)
        self.mode=mode
        self.db=sqlite3.connect(path,isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL").fetchone()
        self.db.execute("PRAGMA synchronous=FULL")
        if create:
            self.db.execute(SCHEMA)
            self.db.execute(POST)
            if mode=="split":
                self.db.execute("CREATE TABLE live(j INTEGER PRIMARY KEY)")
                self.db.execute("CREATE TABLE cold_file(f INTEGER PRIMARY KEY)")
        self.next_id=self.db.execute("SELECT COALESCE(MAX(j),-1)+1 FROM event").fetchone()[0]
        self.fresh = create
        self.owned={}
        self.live={}
        self.owners=Counter()
        self.incident=defaultdict(set)
        self.cold=set()
        self.restore_rows=0
        self.restore_payload=0
        if mode=="split":
            self.cold={f for f, in self.db.execute("SELECT f FROM cold_file")}
            self.restore_rows+=len(self.cold)
            for j,blob in self.db.execute("SELECT l.j,e.members FROM live l JOIN event e ON l.j=e.j ORDER BY l.j"):
                ids=decode(blob);self.live[j]=ids
                self.restore_rows+=1;self.restore_payload+=len(blob)
                for f in ids:
                    self.incident[f].add(j)
                    self.owned[f]=(*self.owned.get(f,()),j)[-B:]
            for values in self.owned.values():self.owners.update(values)
            if set(self.owners)!=set(self.live):raise ValueError("inconsistent hot tier")

    def append(self,j,rev,ids,fault=False):
        ids=tuple(ids)
        if len(ids)<2 or len(set(ids))!=len(ids):raise ValueError("invalid event")
        blob=encode(ids)
        if j<self.next_id:
            if self.db.execute("SELECT rev,members FROM event WHERE j=?",(j,)).fetchone()!=(rev,blob):
                raise ValueError("conflicting replay")
            return False
        if j!=self.next_id:raise ValueError("event gap")
        advance={}
        released=Counter()
        if self.mode=="split":
            for f in ids:
                own=self.owned.get(f,())
                if len(own)==B:released[own[0]]+=1
                advance[f]=(*own,j)[-B:]
        elif self.mode=="own":
            # Hydrate an evicted RAM cache lazily after restart when this file is first updated.
            for f in ids:
                tail,older=self._tail(f)
                advance[f]=(((*tail,(j,ids))[-B:]),older or len(tail)==B)
        expired=sorted(old for old,n in released.items() if self.owners[old]==n)
        added_cold=set()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT INTO event VALUES(?,?,?)",(j,rev,blob))
            if self.mode=="split":
                self.db.execute("INSERT INTO live VALUES(?)",(j,))
                for old in expired:
                    self.db.execute("DELETE FROM live WHERE j=?",(old,))
                    members=self.live[old]
                    self.db.executemany("INSERT INTO post VALUES(?,?)",((f,old) for f in members))
                    added_cold.update(members)
                added_cold-=self.cold
                self.db.executemany("INSERT INTO cold_file VALUES(?)",((f,) for f in sorted(added_cold)))
            else:
                self.db.executemany("INSERT INTO post VALUES(?,?)",((f,j) for f in ids))
            if fault:raise RuntimeError("injected rollback")
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        self.owned.update(advance)
        if self.mode=="split":
            self.owners.subtract(released)
            self.owners[j]=len(ids)
            self.live[j]=ids
            for f in ids:self.incident[f].add(j)
            for old in expired:
                del self.owners[old]
                for f in self.live.pop(old):self.incident[f].remove(old)
            self.cold.update(added_cold)
        self.next_id+=1
        return True

    def _tail(self,f):
        if f in self.owned:return self.owned[f]
        if self.fresh:
            return (), False
        rows=self.db.execute("SELECT p.j,e.members FROM post p JOIN event e ON p.j=e.j "
                             "WHERE p.f=? ORDER BY p.j DESC LIMIT ?",(f,B+1)).fetchall()
        self.restore_rows+=len(rows);self.restore_payload+=sum(len(blob) for j,blob in rows)
        value=(tuple((j,decode(blob)) for j,blob in reversed(rows[:B])),len(rows)>B)
        self.owned[f]=value
        return value

    def read(self,f,tie,prior):
        counts=Counter()
        reads=0;want=True
        if self.mode=="split":
            for j in self.incident.get(f,()):counts.update(self.live[j])
            want=f in self.cold
        elif self.mode=="own":
            tail,older=self._tail(f)
            for j,members in tail:counts.update(members)
            want=older
        if want:
            command,args=READ,(f,)
            if self.mode=="own":
                command+=" AND p.j<?";args=(f,tail[0][0])
            rows=self.db.execute(command,args).fetchall()
            for blob, in rows:
                reads+=len(blob);counts.update(decode(blob))
            return best(counts,f,tie,prior),(1,len(rows),reads)
        return best(counts,f,tie,prior),(0,0,0)

    def close(self):
        self.db.close()
