"""Volatile exact readers on the identical Round 57 durable filelist schema."""
from collections import Counter, OrderedDict, defaultdict, deque
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parents[1]/"block_index"
sys.path.insert(0,str(BASE))
from block_store import BlockStore, unpack
from store import best

CAP=8
MODES=("flat","own","shared","lru")
# Returned work, one row per query: lookup calls, posting BLOBs/bytes, source
# calls, source BLOBs/bytes, hot event bodies decoded, exact LRU hits.
ZERO=(0,0,0,0,0,0,0,0)


class Hot:
    def __init__(self):
        self.owned={}
        self.owners=Counter()
        self.live={}
        self.incident=defaultdict(set)
        self.lost_own=set()
        self.lost_shared=set()
        self.members=0
        self.refs=0

    def append(self,j,ids):
        self.live[j]=ids
        self.members+=len(ids)
        self.owners[j]=len(ids)
        for f in ids:
            self.incident[f].add(j)
            owned=self.owned.get(f)
            if owned is None:
                owned=self.owned[f]=deque()
            if len(owned)==CAP:
                old=owned.popleft()
                self.lost_own.add(f)
                self.owners[old]-=1
                if self.owners[old]==0:
                    del self.owners[old]
                    body=self.live.pop(old)
                    self.members-=len(body)
                    for g in body:
                        self.incident[g].remove(old)
                        self.lost_shared.add(g)
            else:
                self.refs+=1
            owned.append(j)

    def budget(self):
        return 8*len(self.live)+8*self.members+4*self.refs+4*len(self.lost_shared)


class ScoreLRU:
    """Whole immutable-prefix count maps; keep cached counters exact on append."""
    def __init__(self):
        self.maps=OrderedDict()
        self.charge=0
        self.budget=0

    @staticmethod
    def size(counts):
        return 8+8*len(counts)

    def trim(self):
        while self.budget is not None and self.charge>self.budget:
            _,old=self.maps.popitem(last=False)
            self.charge-=self.size(old)

    def append(self,ids,budget):
        self.budget=budget
        for f in ids:
            prior=self.maps.get(f)
            if prior is not None:
                n=len(prior)
                for g in ids:
                    if g!=f:prior[g]+=1
                self.charge+=8*(len(prior)-n)
        self.trim()

    def get(self,f):
        value=self.maps.get(f)
        if value is not None:self.maps.move_to_end(f)
        return value

    def admit(self,f,counts):
        size=self.size(counts)
        if self.budget is not None and size>self.budget:return
        self.maps[f]=counts
        self.charge+=size
        self.trim()


class Reader:
    def __init__(self,path,mode,create=False):
        if mode not in (*MODES,"lru_unbounded"):raise ValueError(mode)
        self.mode=mode
        self.store=BlockStore(path,"filelist",create)
        self.db=self.store.db
        self.fence=self.store.next_id
        self.known_new=set()
        self.hot=Hot() if mode in ("own","shared") else None
        self.lru=ScoreLRU() if mode in ("lru","lru_unbounded") else None
        if mode=="lru_unbounded":self.lru.budget=None

    def append(self,j,rev,ids,budget=0,fault=False):
        if not self.store.append(j,rev,ids,fault=fault):return False
        self.remember(j,ids,budget)
        return True

    def remember(self,j,ids,budget):
        if self.hot:self.hot.append(j,ids)
        elif self.lru:self.lru.append(ids,None if self.mode=="lru_unbounded" else budget)

    def _load(self,f,hot_ids,counts):
        row=self.db.execute("SELECT js FROM posting WHERE f=?",(f,)).fetchone()
        if row is None:
            if self.hot and self.fence:self.known_new.add(f)
            return (1,0,0,0,0,0,len(hot_ids),0)
        block=row[0]
        addresses=unpack(block)
        if self.hot and self.fence and addresses[0]>=self.fence:self.known_new.add(f)
        missing=[j for j in addresses if j not in hot_ids] if hot_ids else addresses
        rows,calls=self.store._fetch_events(missing)
        nbytes=0
        for (blob,) in rows:
            nbytes+=len(blob)
            counts.update(unpack(blob))
        return (1,1,len(block),calls,len(rows),nbytes,len(hot_ids),0)

    def read(self,f,tie,prior):
        if self.lru:
            cached=self.lru.get(f)
            if cached is not None:return best(cached,f,tie,prior),(*ZERO[:-1],1)
        counts=Counter()
        if self.hot:
            if self.mode=="own":
                ids=self.hot.owned.get(f,())
                lost=self.hot.lost_own
            else:
                ids=self.hot.incident.get(f,())
                lost=self.hot.lost_shared
            for j in ids:counts.update(self.hot.live[j])
            if f not in lost and (not self.fence or f in self.known_new):
                return best(counts,f,tie,prior),(0,0,0,0,0,0,len(ids),0)
            work=self._load(f,ids,counts)
        else:
            work=self._load(f,(),counts)
        counts.pop(f,None)
        if self.lru:self.lru.admit(f,counts)
        return best(counts,f,tie,prior),work

    def close(self):
        self.store.close()
