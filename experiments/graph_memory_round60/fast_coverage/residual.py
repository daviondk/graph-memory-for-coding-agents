"""Serialized cache of exact nonresident incidences, synchronized with last-copy losses."""
from collections import Counter, deque
from pathlib import Path
import sys
EXP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(EXP/"graph_memory_round59/fast_path"))
sys.path.insert(0,str(EXP/"graph_memory_round60/coverage"))
from fast_postings import Fast, add, build, contains, first, unpack_full
from coverage import Coverage, possible_losses
from lazy_reader import BlockStore, Cache, EVENT, Hot, Policy, POST, best, unpack, varints
from run_lazy import load, prepare, save

COUNT, BARE=7,8

def v(n):
    return bytes([n]) if n<128 else varints((n,))

class CapturedBodies(dict):
    """Intercept the exact last-owner deletion already performed by Hot.append."""
    def __init__(self):
        super().__init__()
        self.losses=[]
    def pop(self,j):
        body=super().pop(j)
        self.losses.append((j,body))
        return body

class LossCache(Cache):
    def __init__(self,budget):
        super().__init__(budget)
        self.losses=deque()
    def drop(self,key):
        if key[0]==EVENT:
            self.losses.append((key[1],self.items[key]))
        super().drop(key)

class Residual(Policy):
    def __init__(self,store,budget,mode):
        super().__init__(store,Hot(),"joint",budget)
        self.mode=mode
        self.hot.live=CapturedBodies()
        self.cache=LossCache(budget)
        self.seen=store.next_id
        self.stats=Counter()
    def invalidate(self):
        self.hot=Hot()
        self.hot.live=CapturedBodies()
        self.cache=LossCache(self.cache.limit)
        self.known.clear()
        self.fence=self.seen=self.store.next_id
        self.stats["resets"]+=1
    def enroll(self,j,files):
        packed=None
        entries=self.cache.items
        for f in files:
            key=(POST,f)
            data=entries.get(key)
            if data is None or data[0]<COUNT:continue
            if packed is None:packed=v(j)
            offset=1 if data[0]==BARE else 1+first(data[1:])[1]
            if not contains(data[offset:],packed):
                self.cache.put(key,data+packed,refresh=False)
                self.stats["exception_inserts"]+=1
    def drain(self):
        q=self.cache.losses
        self.stats["max_lru_backlog"]=max(self.stats["max_lru_backlog"],len(q))
        while q:
            j,body=q.popleft()
            if j not in self.hot.live and (EVENT,j) not in self.cache.items:
                self.enroll(j,unpack(body))
                self.stats["decoded_evicted_bytes"]+=len(body)
    def committed(self,j,files):
        if j!=self.seen or self.store.next_id!=j+1:
            self.invalidate()
            return
        try:
            self.hot.append(j,files)
            if self.mode!="residual_only":
                for f in files:
                    key=(POST,f)
                    prior=self.cache.items.get(key)
                    if prior is None or prior[0]==BARE:continue
                    if prior[0]==COUNT:
                        n,pos=first(prior[1:])
                        packet=bytes((COUNT,))+v(n+1)+prior[pos+1:]
                    else:packet=add(prior,j)
                    self.cache.put(key,packet,refresh=False)
                    self.cache.updates+=1
            lost=self.hot.live.losses
            self.stats["max_hot_backlog"]=max(self.stats["max_hot_backlog"],len(lost))
            for old,body in lost:
                if (EVENT,old) not in self.cache.items:
                    self.enroll(old,body)
            lost.clear()
            if self.cache.losses:self.drain()
            self.seen=j+1
        except BaseException:
            self.invalidate()
            raise
    def read(self,f,tie,prior):
        if self.store.next_id!=self.seen:self.invalidate()
        try:return self._query(f,tie,prior)
        except BaseException:
            self.invalidate()
            raise
    def _query(self,f,tie,prior):
        hot=self.hot.incident.get(f,())
        counts=Counter()
        stats=Counter()
        for j in hot:counts.update(self.hot.live[j])
        if f not in self.known or f in self.hot.lost_shared:
            key=(POST,f)
            packet=self.cache.get(key)
            ids=None
            if packet is not None:
                if packet[0]<COUNT:
                    ids=unpack_full(packet)
                else:
                    n=None
                    offset=1
                    if packet[0]==COUNT:
                        n,p=first(packet[1:])
                        offset+=p
                    known=set(unpack(packet[offset:]))
                    known.update(hot)
                    needle=v(f) if f>=0 else None
                    if needle:
                        for (kind,j),body in self.cache.items.items():
                            if kind==EVENT and j not in known and contains(body,needle):
                                known.add(j)
                    if n is None or n==len(known):
                        ids=sorted(known)
                        stats["certified"]+=1
                    else:stats["fallback"]+=1
            if ids is None:
                row=self.store.db.execute("SELECT js FROM posting WHERE f=?",(f,)).fetchone()
                body=row[0] if row else b""
                ids=unpack(body)
                stats["posting_calls"]+=1;stats["posting_bytes"]+=len(body)
            if not ids or ids[0]>=self.fence:self.known.add(f)
            missing=[]
            for j in ids:
                if j in hot:continue
                b=self.cache.get((EVENT,j))
                if b is None:missing.append(j)
                else:counts.update(unpack(b))
            for start in range(0,len(missing),400):
                batch=missing[start:start+400]
                qs=",".join("?" for _ in batch)
                rows=self.store.db.execute("SELECT members FROM event WHERE j IN ("+qs+") ORDER BY j",batch).fetchall()
                assert len(batch)==len(rows)
                stats["body_calls"]+=1
                for j,(b,) in zip(batch,rows):
                    counts.update(unpack(b));stats["body_bytes"]+=len(b)
                    self.cache.put((EVENT,j),b,admission=f)
                if self.cache.losses:self.drain()
            suffix=varints(j for j in ids if j not in hot and (EVENT,j) not in self.cache.items)
            if self.mode=="native_count":
                packet=bytes((COUNT,))+v(len(ids))+suffix
            else:packet=bytes((BARE,))+suffix
            if self.mode!="residual_only":
                candidate=build(ids)
                if len(candidate)<=len(packet):packet=candidate
            self.cache.put(key,packet)
            if self.cache.losses:self.drain()
        counts.pop(f,None)
        return best(counts,f,tie,prior),stats

