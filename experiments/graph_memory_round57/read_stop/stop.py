"""Exact top-k certification while accessing archive payloads only through a read callback."""
from collections import Counter
from functools import lru_cache
from hashlib import blake2b
from heapq import nlargest
from math import lcm

UNIT=lcm(*range(1,64))
MODES=("sizes","bloom32","bloom64","inline4","inline8")

def encode(ids):
    buf=bytearray();last=0
    for x in sorted(ids):
        v=x-last;last=x
        while v>=128:buf.append(128+(v&127));v>>=7
        buf.append(v)
    return bytes(buf)

def decode(payload,size):
    it=iter(payload);out=[];last=0
    for _ in range(size):
        v=0;shift=0
        while True:
            n=next(it);v|=(n&127)<<shift
            if n<128:break
            shift+=7
        last+=v;out.append(last)
    assert list(it)==[] and len(set(out))==size
    return out

@lru_cache(maxsize=131072)
def bits(x,width):
    raw=blake2b(x.to_bytes(4,"little"),person=b"read-stop-57",digest_size=8).digest()
    a=int.from_bytes(raw[:4],"little")%width
    b=int.from_bytes(raw[4:],"little")%width
    return (1<<a)|(1<<b)

def prepare_meta(mode,ids,payload):
    if mode=="sizes":return b""
    if mode.startswith("bloom"):
        width=int(mode[5:]);value=0
        for x in ids:value|=bits(x,width)
        return value.to_bytes(width//8,"little")
    budget=int(mode[6:])
    return bytes([len(payload)])+payload if len(payload)<budget else b"\0"

def test_order(count,lo,width,tie,anchor):
    pool=(x for x in range(count) if x!=anchor)
    leaders=nlargest(8,pool,key=lambda x:(lo[x],tie[x],-x))
    if not leaders:return [],True,True
    top=set(leaders)
    def upper(x):return lo[x]+width(x),tie[x],-x
    high=max((upper(x) for x in range(count) if x!=anchor and x not in top),default=None)
    ordered=True
    for x in reversed(leaders):
        lower=lo[x],tie[x],-x
        if high is not None and lower<=high:ordered=False;break
        val=upper(x)
        if high is None or val>high:high=val
    return leaders,ordered,ordered and all(width(x)==0 for x in leaders)

def query(mode,headers,meta,count,anchor,tie,reader):
    shard={j:m for j,m in headers}
    lo=Counter();todo=[];upper=[0]*count
    bloom=mode.startswith("bloom")
    width=int(mode[5:]) if bloom else 0
    checks=[bits(x,width) for x in range(count)] if bloom else []
    filters={}
    unknown=0
    for j,m in headers:
        w=UNIT//(m-1);item=meta[j]
        if mode.startswith("inline") and item[0]:
            assert len(item)==item[0]+1
            for x in decode(item[1:],m):lo[x]+=w
            continue
        todo.append(j);unknown+=w
        if bloom:
            tag=int.from_bytes(item,"little")
            match=[x for x,mask in enumerate(checks) if tag&mask==mask]
            filters[j]=match
            for x in match:upper[x]+=w
    width_at=upper.__getitem__ if bloom else lambda _:unknown
    payload_bytes=0;visited=[];early=None
    while True:
        rank,ids,exact=test_order(count,lo,width_at,tie,anchor)
        if ids and early is None:
            early=(list(rank),list(visited),payload_bytes)
        if exact:
            assert rank==early[0]
            return dict(rank=rank,scores=[lo[x] for x in rank],ids_reads=early[1],ids_bytes=early[2],
                        score_reads=visited,score_bytes=payload_bytes)
        j=todo[len(visited)];m=shard[j];w=UNIT//(m-1)
        raw=reader(j)
        for x in decode(raw,m):lo[x]+=w
        if bloom:
            for x in filters[j]:upper[x]-=w
        unknown-=w;visited.append(j);payload_bytes+=len(raw)
