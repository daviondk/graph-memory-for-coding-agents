"""Build from old sets only. No timestamps, change sets, future labels or data-dependent oracle."""
from collections import Counter
from functools import lru_cache
import math,struct,zlib
import numpy as np
from reader import hash_lanes,xor_lanes

def packed(values,w):
    arr=np.asarray(values,dtype=np.uint32)
    bitmap=((arr[:,None]>>np.arange(w,dtype=np.uint32))&1).astype(np.uint8).reshape(-1)
    return np.packbits(bitmap,bitorder='little').tobytes()
def pad(data,cap):
    if len(data)>cap:raise ValueError('Over budget')
    return data+bytes(cap-len(data))
def digest_array(keys,seed):
    return np.array([hash_lanes(seed,0,s) for s in keys],dtype=np.uint32)
@lru_cache(maxsize=16)
def popcounts(n):
    return np.array([v.bit_count() for v in range(1<<n)],dtype=np.uint8)
def occupancy(rows,old_masks,indices,n,k):
    if k==1: votes=rows[indices[:,0]]
    else:votes=np.bitwise_and.reduce(rows[indices[:,:k]],axis=1)
    assert np.all((votes&old_masks)==old_masks)
    present=float((popcounts(n)[votes]-popcounts(n)[old_masks]).mean())/n
    if k==1:absent=float(popcounts(n)[rows].mean())/n
    else:absent=sum(float(np.mean((rows>>i)&1))**k for i in range(n))/n
    return .5*(present+absent)
def rows_for(m,k,h,old_masks):
    indices=h[:,:k]%m
    rows=np.zeros(m,dtype=np.uint16)
    for j in range(k):np.bitwise_or.at(rows,indices[:,j],old_masks)
    return rows,indices
def flat(n,seed,cap,keys,masks,card,k_fixed=None):
    hs=digest_array(keys,seed);m=(cap-4)*8//n
    k=k_fixed or min(range(1,9),key=lambda k:sum((1-(1-1/m)**(k*c))**k for c in card))
    r,idx=rows_for(m,k,hs,masks)
    raw=bytes([1,n,seed,k])+packed(r,n)
    loss=occupancy(r,masks,idx,n,k)
    return pad(raw,cap),{'type':'bucket' if k_fixed else 'flat_bloofi','k':k,'m':m,'used':len(raw),'risk':loss}
def sparse(n,seed,cap,keys,masks,card):
    h=digest_array(keys,seed);basic=(cap-4)*8//n
    r,idx=rows_for(basic,1,h,masks)
    raw=bytes([1,n,seed,1])+packed(r,n)
    best=(occupancy(r,masks,idx,n,1),len(raw),raw,{'type':'bucket_fallback','m':basic,'n_classes':None})
    width=(n+7)//8
    for m in sorted({max(2,int(basic*factor)) for factor in (.5,1,2,4,8,16)}):
        r,idx=rows_for(m,1,h,masks)
        classes,codes=np.unique(r,return_inverse=True)
        clas=classes.astype('u1' if width==1 else '<u2').tobytes()
        enc=zlib.compress(codes.astype('u1' if len(classes)<=256 else '<u2').tobytes(),1)
        raw=bytes([2,n,seed])+struct.pack('<IH',m,len(classes))+clas+enc
        if len(raw)>cap:continue
        loss=occupancy(r,masks,idx,n,1)
        candidate=(loss,len(raw),raw,{'type':'dictionary','m':m,'n_classes':len(classes)})
        if candidate[:2]<best[:2]:best=candidate
    loss,used,raw,meta=best
    return pad(raw,cap),dict(**meta,used=used,risk=loss)
def choose_colors(n,masks,cap,length):
    freq=Counter(map(int,masks));full=(1<<n)-1
    order=sorted((m for m in freq if m!=full),key=lambda m:(-freq[m],m))
    trials=sorted({1,min(len(order)+1,2),min(len(order)+1,4),min(len(order)+1,8),
                   min(len(order)+1,16),min(len(order)+1,32),min(len(order)+1,64),len(order)+1})
    best=None; width=(n+7)//8
    for count in trials:
        codes=[full]+order[:count-1]
        w=min(24,(cap-(9+count*width))*8//(3*length))
        if w<1 or (1<<w)<count:continue
        idx={m:j for j,m in enumerate(codes)}
        lift={}
        for mask in freq:
            if mask in idx:lift[mask]=idx[mask];continue
            lift[mask]=min((j for j,c in enumerate(codes) if (c&mask)==mask),key=lambda j:(codes[j].bit_count(),j))
        miss=sum(f*(codes[lift[m]].bit_count()-m.bit_count()) for m,f in freq.items())/(len(masks)*n)
        absent=sum(m.bit_count() for m in codes)/((1<<w)*n)
        loss=.5*(miss+absent)
        if best is None or loss<best[0]:best=(loss,w,codes,lift)
    return best
def peel(keys,seed,retry,length):
    hv=[xor_lanes(seed,retry,k) for k in keys]
    cells=[(a%length,length+b%length,2*length+c%length) for a,b,c,_ in hv]
    nslot=3*length
    degree=[0]*nslot;accum=[0]*nslot
    for i,row in enumerate(cells):
        for c in row:degree[c]+=1;accum[c]^=i
    stack=[i for i,d in enumerate(degree) if d==1];seq=[]
    while stack:
        c=stack.pop()
        if degree[c]!=1:continue
        edge=accum[c];seq.append((edge,c))
        for k in cells[edge]:
            degree[k]-=1;accum[k]^=edge
            if degree[k]==1:stack.append(k)
    return (seq,cells,hv) if len(seq)==len(keys) else None
def xormap(n,seed,cap,keys,masks,card):
    length=math.ceil((1.23*len(keys)+32)/3)
    fit=choose_colors(n,masks,cap,length)
    if fit is not None:
        loss,w,codes,lift=fit;limit=(1<<w)-1
        for retry in range(8):
            solution=peel(keys,seed,retry,length)
            if solution is None:continue
            seq,cells,hv=solution
            registers=[0]*(3*length)
            for i,c in reversed(seq):
                a,b,d=cells[i]
                registers[c]=lift[int(masks[i])]^(hv[i][3]&limit)^registers[a]^registers[b]^registers[d]
            width=(n+7)//8
            raw=bytes([3,n,seed])+struct.pack('<HBBH',length,w,retry,len(codes))
            raw+=b''.join(m.to_bytes(width,'little') for m in codes)+packed(registers,w)
            return pad(raw,cap),{'type':'xor_map','retry':retry,'w':w,'classes':len(codes),'class_bytes':len(codes)*width,'slots':3*length,'used':len(raw),'risk':loss}
    data,meta=flat(n,seed,cap,keys,masks,card,1)
    return data,dict(meta,type='xor_fallback_capacity' if fit is None else 'xor_fallback_peeling')
