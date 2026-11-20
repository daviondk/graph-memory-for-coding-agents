"""Fit the bit allocation before any change query and serialize the entire addressable state."""
import functools
import hashlib
import math
import struct


def false_positive(n,size,k):
    if not n:return 0.
    if not size:return 1.
    return (-math.expm1(k*n*math.log1p(-1/(8*size))))**k


def best_k(n,size):
    if not n:return 0
    return min(range(1,9),key=lambda k:false_positive(n,size,k))


def split_weight(size,weights):
    active=[i for i,w in enumerate(weights) if w]
    if not active:return [0]*len(weights)
    if size<len(active):raise ValueError("insufficient budget")
    out=[int(w>0) for w in weights]
    room=size-len(active)
    den=sum(weights)
    for i in active:out[i]+=room*weights[i]//den
    for i in sorted(active,key=lambda i:(-(room*weights[i]%den),i))[:size-sum(out)]:out[i]+=1
    return out


def flat_lengths(budget,n,tag):
    available=budget-1-(n if tag==1 else 0)
    return [available//n+int(i<available%n) for i in range(n)]


def expected(tag,sizes,ks,sets):
    ps=[false_positive(len(s),size,k) for s,size,k in zip(sets,sizes,ks)]
    if tag==2:return sum(ps[0]+(1-ps[0])*p for p in ps[1:])/(len(ps)-1)
    return sum(ps)/len(ps)


def layout(allsets,budget):
    n=len(allsets)
    result={}
    for mode,tag in (("fixed",0),("adaptive_flat",1)):
        sz=flat_lengths(budget,n,tag)
        ks=[4]*n if tag==0 else [best_k(len(s),m) for s,m in zip(allsets,sz)]
        result[mode]=(expected(tag,sz,ks,allsets),tag,sz,ks,allsets)
    common=set.intersection(*allsets)
    residues=[s-common for s in allsets]
    sets=[common,*residues]
    spare=budget-1-3*(n+1)
    candidates=[]
    for step in range(1,20):
        cs=spare*step//20 if common else 0
        if not any(residues):cs=spare
        if spare-cs<sum(bool(s) for s in residues):continue
        sz=[cs,*split_weight(spare-cs,[len(s) for s in residues])]
        ks=[best_k(len(s),m) for s,m in zip(sets,sz)]
        candidates.append((expected(2,sz,ks,sets),2,sz,ks,sets))
    result["factored"]=min(candidates,key=lambda c:c[0])
    result["selected"]=min((result["adaptive_flat"],result["factored"]),key=lambda c:c[0])
    return result


@functools.lru_cache(maxsize=35000)
def addresses(seed,family,key):
    raw=hashlib.blake2b(key.encode(),digest_size=32,person=b"R9matrix",salt=struct.pack("<II",seed,family)).digest()
    return struct.unpack("<8I",raw)


def encoded(table,seed):
    _,tag,sizes,ks,sets=table
    buf=bytearray([tag])
    if tag==1:buf.extend(ks)
    if tag==2:
        for size,k in zip(sizes,ks):buf.extend(struct.pack("<HB",size,k))
    for i,(size,k,keys) in enumerate(zip(sizes,ks,sets)):
        bits=bytearray(size)
        family=int(tag==2 and i==0)
        for key in keys:
            for h in addresses(seed,family,key)[:k]:
                bit=h%(size*8)
                bits[bit//8]|=1<<(bit%8)
        buf.extend(bits)
    return bytes(buf)


def decoded(payload,n):
    tag=payload[0]
    if tag==2:
        pos=1+3*(n+1)
        headers=list(struct.iter_unpack("<HB",payload[1:pos]))
    else:
        pos=1+(n if tag==1 else 0)
        ks=list(payload[1:pos]) if tag==1 else [4]*n
        headers=zip(flat_lengths(len(payload),n,tag),ks)
    slots=[]
    for size,k in headers:
        slots.append((payload[pos:pos+size],k))
        pos+=size
    assert pos==len(payload)
    return tag,slots


def has(state,idx,query,seed):
    tag,slots=state
    for j,family in ([(0,1),(idx+1,0)] if tag==2 else [(idx,0)]):
        data,k=slots[j]
        if not data or not k:continue
        for key in query:
            bits=[h%(8*len(data)) for h in addresses(seed,family,key)[:k]]
            if all(data[b//8] & (1<<(b%8)) for b in bits):return True
    return False
