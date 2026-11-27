"""Exact incidence sketches over an append-only event graph."""
from collections import Counter
from functools import reduce
from itertools import accumulate
from math import isqrt
from operator import xor
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lazy"))
from lazy_reader import EVENT,POST,Policy,best,varints,unpack

ABS,DELTA,BITS,NUM,XOR,MOMENTS=range(6)


def full(ids):
    absolute=bytes([ABS])+varints(ids)
    if not ids:return absolute
    gaps=varints(j-k-1 for j,k in zip(ids,(-1,*ids[:-1])))
    layouts=[absolute,bytes([DELTA])+gaps]
    span=ids[-1]-ids[0]+1
    if (span+7)//8<len(min(layouts,key=len)):
        bits=bytearray((span+7)//8)
        for j in ids:
            n=j-ids[0]
            bits[n//8]|=1<<(n%8)
        layouts.append(bytes([BITS])+varints((ids[0],))+bytes(bits))
    return min(layouts,key=len)


def expand(packet):
    kind=packet[0]
    body=packet[1:]
    if kind==ABS:return unpack(body)
    if kind==DELTA:return tuple(j-1 for j in accumulate(v+1 for v in unpack(body)))
    if kind==BITS:
        end=next(i+1 for i,b in enumerate(body) if b<128)
        start,=unpack(body[:end])
        return tuple(start+8*p+i for p,x in enumerate(body[end:]) for i in range(8) if x&(1<<i))
    raise ValueError("not a complete list")


def encode(ids,kind):
    exact=full(ids)
    if kind is None:return exact
    fields=[len(ids)]
    if kind==XOR:fields.append(reduce(xor,ids,0))
    if kind==MOMENTS:fields.extend((sum(ids),sum(j*j for j in ids)))
    short=bytes([kind])+varints(fields)
    return short if len(short)<len(exact) else exact


def append(packet,j):
    kind=packet[0]
    if kind<NUM:return full((*expand(packet),j))
    v=list(unpack(packet[1:]))
    v[0]+=1
    if kind==XOR:v[1]^=j
    if kind==MOMENTS:
        v[1]+=j
        v[2]+=j*j
    return bytes([kind])+varints(v)


def restore(packet, present, end):
    kind=packet[0]
    fields=unpack(packet[1:])
    deficit=fields[0]-len(present)
    if deficit==0:return tuple(sorted(present)),0
    if deficit==1 and kind==XOR:
        new=(fields[1]^reduce(xor,present,0),)
    elif deficit in (1,2) and kind==MOMENTS:
        s=fields[1]-sum(present)
        ss=fields[2]-sum(x*x for x in present)
        if deficit==1:
            if s*s!=ss:return None,deficit
            new=(s,)
        else:
            square=2*ss-s*s
            if square<=0:return None,deficit
            d=isqrt(square)
            if d*d!=square or (s-d)%2:return None,deficit
            new=((s-d)//2,(s+d)//2)
    else:
        return None,deficit
    if any(j<0 or j>=end or j in present for j in new):return None,deficit
    return tuple(sorted((*present,*new))),deficit


class SketchPolicy(Policy):
    def __init__(self,store,hot,kind,limit):
        super().__init__(store,hot,"joint",limit)
        self.kind=kind

    def resident(self,f,hot,stats):
        present=set(hot)
        for (kind,j),data in self.cache.items.items():
            if kind==EVENT:
                stats["scan_bytes"]+=len(data)
                stats["scan_objects"]+=1
                if f in unpack(data):present.add(j)
        return present

    def expand(self,packet):
        return expand(packet)

    def recover(self,record,present):
        return restore(record,present,self.store.next_id)

    def admit(self,f,ids,record,stats):
        return encode(ids,self.kind)

    def after_write(self,j,files):
        for f in files:
            key=(POST,f)
            prior=self.cache.items.get(key)
            if prior is not None:
                self.cache.put(key,append(prior,j),refresh=False)
                self.cache.updates+=1

    def read(self,f,tie,prior):
        counts=Counter()
        stats=Counter()
        hot=self.hot.incident.get(f,())
        for j in hot:counts.update(self.hot.live[j])
        ids=None
        if not(f in self.known and f not in self.hot.lost_shared):
            record=self.cache.get((POST,f))
            if record is not None:
                if record[0]<NUM:
                    ids=self.expand(record)
                    stats["exact_hit"]+=1
                else:
                    present=self.resident(f,hot,stats)
                    ids,diff=self.recover(record,present)
                    stats["failed" if ids is None else "recovered"+str(diff)]+=1
            if ids is None:
                row=self.store.db.execute("SELECT js FROM posting WHERE f=?",(f,)).fetchone()
                data=row[0] if row else b""
                ids=unpack(data)
                stats["posting_bytes"]+=len(data)
                stats["posting_calls"]+=1
            if not ids or ids[0]>=self.fence:self.known.add(f)
            missing=[]
            for j in ids:
                if j in hot:continue
                data=self.cache.get((EVENT,j))
                if data is None:missing.append(j)
                else:counts.update(unpack(data))
            for start in range(0,len(missing),400):
                batch=missing[start:start+400]
                params=",".join("?" for _ in batch)
                rows=self.store.db.execute("SELECT members FROM event WHERE j IN ("+params+") ORDER BY j",batch).fetchall()
                assert len(rows)==len(batch)
                stats["body_calls"]+=1
                for j,(body,) in zip(batch,rows):
                    stats["body_bytes"]+=len(body)
                    counts.update(unpack(body))
                    self.cache.put((EVENT,j),body,admission=f)
            self.cache.put((POST,f),self.admit(f,ids,record,stats))
        counts.pop(f,None)
        return best(counts,f,tie,prior),stats
