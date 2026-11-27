"""Zero-preload readers on an append-only SQLite filelist graph."""
from collections import Counter, OrderedDict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"graph_memory_round57"/"composed"))
from reader import Hot, best
from block_store import BlockStore, varints, unpack
from experiment import footprint

EVENT, POST, SCORE, COVER = 0, 1, 2, 3
FIELDS = ("posting_calls","body_calls","posting_bytes","body_bytes","body_rows","event_hits",
          "cross_hits","cross_hit_bytes","posting_hits","score_hits","hot_bodies","cache_size")
ARM = {"flat":("flat",False,0),"B8":("flat",True,0)}
for limit in (1024,4096):
    for heated in (False,True):
        for policy in ("joint","events","counts","postings"):
            ARM[f"{'B8' if heated else 'pure'}-{policy}-{limit}"]=(policy,heated,limit)


def width(n):
    return max(1,(n.bit_length()+6)//7)


def entry_size(key,blob):
    return 1 + width(key[1]+1) + width(len(blob)) + len(blob)


def encode_scores(counts):
    return varints(v for p in sorted(counts.items()) for v in p)


def decode_scores(blob):
    pairs=iter(unpack(blob))
    return Counter(dict(zip(pairs,pairs)))


class Cache:
    def __init__(self,limit):
        self.limit=limit
        self.items=OrderedDict()
        self.size=self.peak=self.updates=self.evicted=0
        # Admission anchors are observational labels and never affect cache decisions.
        self.origin={}

    def get(self,key):
        blob=self.items.get(key)
        if blob is not None:self.items.move_to_end(key)
        return blob

    def drop(self,key):
        val=self.items.pop(key)
        self.size-=entry_size(key,val)
        if key[0]==EVENT:self.origin.pop(key[1],None)

    def put(self,key,blob,admission=None,refresh=True):
        old=self.items.get(key)
        charge=entry_size(key,blob)
        if charge>self.limit:
            if old is not None:self.drop(key)
            return
        if old is not None:self.size-=entry_size(key,old)
        self.items[key]=blob
        self.size+=charge
        if refresh:self.items.move_to_end(key)
        if key[0]==EVENT:self.origin[key[1]]=admission
        while self.size>self.limit:
            self.drop(next(iter(self.items)))
            self.evicted+=1
        self.peak=max(self.peak,self.size)

    def inventory(self):
        serialized=b"".join(bytes([kind])+varints((ident+1,len(blob)))+blob
                            for (kind,ident),blob in self.items.items())
        assert self.size==len(serialized)<=self.limit
        return dict(packed=self.size,python=footprint(self.items),peak=self.peak,updated=self.updates,
                    evicted=self.evicted,records=len(self.items))


class Policy:
    def __init__(self,store,hot,mode,limit):
        self.store=store
        self.fence=store.next_id
        self.hot=hot
        self.known=set()
        self.cache=Cache(limit)
        self.events=mode in ("joint","events")
        self.postings=mode in ("joint","postings")
        self.scores=mode=="counts"

    def after_write(self,j,files):
        if self.postings:
            suffix=varints((j,))
            for f in files:
                key=(POST,f)
                prior=self.cache.items.get(key)
                if prior is not None:
                    self.cache.put(key,prior+suffix,refresh=False)
                    self.cache.updates+=1
        if self.scores:
            for f in files:
                key=(SCORE,f)
                raw=self.cache.items.get(key)
                if raw is not None:
                    counts=decode_scores(raw)
                    counts.update(g for g in files if g!=f)
                    self.cache.put(key,encode_scores(counts),refresh=False)
                    self.cache.updates+=1

    def read(self,f,tie,prior):
        counts=Counter()
        stats=[0]*len(FIELDS)
        if self.scores:
            blob=self.cache.get((SCORE,f))
            if blob is not None:
                stats[9]=1
                stats[-1]=self.cache.size
                return best(decode_scores(blob),f,tie,prior),stats
        pinned=self.before(f)
        for event in pinned.values():counts.update(event)
        hot=self.hot.incident.get(f,()) if self.hot is not None else ()
        for j in hot:counts.update(self.hot.live[j])
        stats[10]=len(hot)
        fresh=self.hot is not None and f not in self.hot.lost_shared and (f in self.known or self.covered(f))
        if not fresh:
            blob=self.cache.get((POST,f)) if self.postings else None
            if blob is None:
                row=self.store.db.execute("SELECT js FROM posting WHERE f=?",(f,)).fetchone()
                blob=row[0] if row else b""
                stats[0]=1;stats[2]=len(blob)
            else:
                stats[8]=1
            ids=unpack(blob)
            if self.hot is not None and (not ids or ids[0]>=self.fence):self.known.add(f)
            elif pinned:self.certify(f,ids,pinned)
            missing=[]
            for j in ids:
                if j in hot or j in pinned:continue
                event=self.cache.get((EVENT,j)) if self.events else None
                if event is None:
                    missing.append(j)
                else:
                    counts.update(unpack(event));stats[5]+=1
                    if self.cache.origin[j]!=f:
                        stats[6]+=1;stats[7]+=len(event)
            for start in range(0,len(missing),400):
                batch=missing[start:start+400]
                assert batch==sorted(batch)
                qs=",".join("?" for _ in batch)
                # Canonical sorted IDs establish correspondence without transferring IDs back.
                rows=self.store.db.execute("SELECT members FROM event WHERE j IN ("+qs+") ORDER BY j",batch).fetchall()
                assert len(rows)==len(batch)
                stats[1]+=1;stats[4]+=len(rows)
                for j,(event,) in zip(batch,rows):
                    stats[3]+=len(event)
                    counts.update(unpack(event))
                    if self.events:self.cache.put((EVENT,j),event,admission=f)
            if self.postings:self.cache.put((POST,f),blob)
        counts.pop(f,None)
        if self.scores:self.cache.put((SCORE,f),encode_scores(counts))
        stats[-1]=self.cache.size
        return best(counts,f,tie,prior),stats

    def before(self,f):
        return {}

    def covered(self,f):
        return False

    def certify(self,f,ids,pinned):
        pass
