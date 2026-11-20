"""A byte-complete lossless range read. Client, authoritative source, and receiver share no hidden cache."""
import hashlib
import itertools
import struct
import zlib

import brotli

FLAT=("full","whole","pages","runs","lean_runs")
ALL=FLAT+("joint","epoch")
ARMS=("lru","point","typed")

def uint(n):
    assert n>=0
    out=bytearray()
    while n>=128:
        out.append((n&127)|128);n>>=7
    out.append(n)
    return bytes(out)

class Reader:
    def __init__(self,raw):self.raw=raw;self.i=0
    def take(self,n):
        chunk=self.raw[self.i:self.i+n];self.i+=n
        assert len(chunk)==n
        return chunk
    def num(self):
        x=0;k=0
        while True:
            b=self.take(1)[0];x|=(b&127)<<k
            if b<128:return x
            k+=7
    def string(self):return self.take(self.num())

def lp(b):return uint(len(b))+b
def compact(raw):
    # Identical backend choice for all controls, including the whole-message baseline.
    return min([b"0"+raw,b"1"+zlib.compress(raw,6),b"2"+brotli.compress(raw,quality=4)],key=len)
def unpack(frame):
    kind,raw=frame[:1],frame[1:]
    if kind==b"0":return raw
    if kind==b"1":return zlib.decompress(raw)
    assert kind==b"2"
    return brotli.decompress(raw)
def spans(ii):
    output=[]
    for n in sorted(ii):
        if output and n==output[-1][1]+1:output[-1]=(output[-1][0],n)
        else:output.append((n,n))
    return output
def ids(segments):
    return (n for a,b in segments for n in range(a,b+1))
def loc(segments):
    out=bytearray(uint(len(segments)));prev=0
    for a,b in segments:
        out.extend(uint(a-prev-1));out.extend(uint(b-a));prev=b
    return bytes(out)
def readloc(r):
    prev=0;segments=[]
    for _ in range(r.num()):
        a=prev+1+r.num();b=a+r.num();segments.append((a,b));prev=b
    return segments
def hashmsg(items,segments):
    h=hashlib.blake2b(digest_size=16)
    for n in ids(segments):h.update(lp(items[n]))
    return h.digest()
def contents(ss,path,vr):
    lo,hi=vr or (1,-1)
    d={}
    for p,info,runs in ss[2]:
        if p!=path:continue
        for first,at,txt in runs:
            for n,line in enumerate(txt,first):
                if lo<=n and (hi==-1 or n<=hi):d[n]=(line.encode(),at)
    return d
def clip(mem,vr):
    if not vr:return mem
    a,b=vr
    return {n:v for n,v in mem.items() if n>=a and (b<0 or n<=b)}
def predictors(rows,vr):
    segments=spans(rows)
    total=sum(len(x[0])+1 for x in rows.values())
    return (int(vr is not None and vr[1]>=0),min(len(segments),3),
            0 if total<256 else 1 if total<1024 else 2 if total<4096 else 3)
def offers(rows,vr,mode):
    if not rows or mode=="full":return []
    parts=spans(rows)
    if mode=="whole":
        lo,hi=vr or (1,-1)
        if len(parts)!=1 or parts[0][0]!=lo or (hi!=-1 and parts[0][1]!=hi):return []
        return [parts]
    if mode=="runs":return [[p] for p in parts]
    if mode=="lean_runs":
        return [[p] for p in parts if len(zlib.compress(b"".join(lp(rows[i][0]) for i in ids([p])),6))>=24]
    if mode=="pages":
        result=[]
        for a,b in parts:
            while a<=b:
                end=min(b,((a-1)//12+1)*12);result.append([(a,end)]);a=end+1
        return result
    if mode=="joint":return [parts]
    if mode=="epoch":
        times={}
        for n,(_,age) in rows.items():times.setdefault(age,[]).append(n)
        return [spans(ch) for _,ch in sorted(times.items())]
    raise ValueError(mode)
def request(path,vr,rows,mode):
    source={n:v[0] for n,v in rows.items()}
    groups=offers(rows,vr,mode)
    out=bytearray(lp(path.encode()))
    out.extend(uint(0 if vr is None else 1))
    if vr is not None:out.extend(uint(vr[0]));out.extend(uint(vr[1]+1))
    # No explicit mode marker is needed when no candidates were sent.
    out.extend(uint(1 if mode=="whole" and groups else 0));out.extend(uint(len(groups)))
    for segments in groups:
        out.extend(loc(segments));out.extend(hashmsg(source,segments))
    return compact(bytes(out))
def parse_request(frame):
    r=Reader(unpack(frame));path=r.string().decode()
    vr=(r.num(),r.num()-1) if r.num() else None
    whole=bool(r.num());groups=[]
    for _ in range(r.num()):groups.append((readloc(r),r.take(16)))
    assert r.i==len(r.raw)
    return path,vr,whole,groups
def whole_frame(authority):
    geometry=spans(authority)
    body=loc(geometry)+b"".join(lp(authority[i]) for i in ids(geometry))
    return b"F"+compact(body)
def serve(frame,authority,full):
    # The source has just the wire packet and its own current returned lines.
    path,vr,whole,groups=parse_request(frame)
    accepted=0;copied=set()
    for j,(segments,digest) in enumerate(groups):
        ix=list(ids(segments))
        if whole and len(ix)!=len(authority):continue
        if any(n not in authority for n in ix):continue
        if hashmsg(authority,segments)!=digest:continue
        assert not copied.intersection(ix)
        accepted|=1<<j;copied.update(ix)
    if not copied:return full,(len(groups),accepted.bit_count(),0)
    geometry=spans(authority)
    mask=accepted.to_bytes((len(groups)+7)//8,"little")
    raw=loc(geometry)+mask+b"".join(lp(authority[n]) for n in ids(geometry) if n not in copied)
    delta=b"P"+compact(raw)
    if len(delta)<len(full):return delta,(len(groups),accepted.bit_count(),len(copied))
    return full,(len(groups),accepted.bit_count(),0)
def receive(req,reply,memory):
    path,vr,_,groups=parse_request(req)
    r=Reader(unpack(reply[1:]))
    geometry=readloc(r)
    copies=set()
    if reply[:1]==b"P":
        mask=int.from_bytes(r.take((len(groups)+7)//8),"little")
        for j,(segments,_) in enumerate(groups):
            if mask&(1<<j):copies.update(ids(segments))
    else:assert reply[:1]==b"F"
    actual={n:(memory[n][0] if n in copies else r.string()) for n in ids(geometry)}
    assert r.i==len(r.raw) and copies<=set(actual)
    return actual
def tests():
    rows={1:(b"alpha"*20,1),2:(b"beta"*20,1),5:(b"g"*160,1),7:(b"z"*40,3)}
    for vr in (None,[1,-1],[1,7]):
        for mode in ALL:
            frame=request("src/text.py",vr,rows,mode)
            for values in ({n:v for n,(v,_) in rows.items()},
                           {1:rows[1][0],2:b"stale",4:b"new",5:rows[5][0]},{}):
                wire,stats=serve(frame,values,whole_frame(values))
                assert receive(frame,wire,rows)==values
if __name__=="__main__":tests()
