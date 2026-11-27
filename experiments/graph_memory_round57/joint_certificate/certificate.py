"""Exact integer interval certificate for the seed_pair two-anchor mixture."""
from collections import Counter,defaultdict
from dataclasses import dataclass,field
from fractions import Fraction
from math import lcm
import struct

UNIT=lcm(*range(1,65))
HEADER=struct.Struct("<BBBBI")
CELL=struct.Struct("<IBB")
PTR=struct.Struct("<I")

@dataclass
class Stratum:
    a:int=0
    b:int=0
    j:int=0
    uv:dict=field(default_factory=dict)
    offsets:list=field(default_factory=list)

def materialize(selected,archive,a,b):
    strata={}; updates=0;members=0
    for j in selected:
        e=archive[j];m=len(e);members+=m
        x_a=a in e;x_b=b in e
        assert x_a or x_b
        s=strata.setdefault(m,Stratum())
        if x_a and x_b:
            s.j+=1
            if m>2:s.offsets.append(j)
        elif x_a:s.a+=1
        else:s.b+=1
        for x in e:
            if x in (a,b):continue
            u,v=s.uv.get(x,(0,0))
            s.uv[x]=(u+x_a,v+x_b)
            updates+=int(x_a)+int(x_b)
    raw=bytearray([len(strata)])
    for m,s in sorted(strata.items()):
        raw.extend(HEADER.pack(m,s.a,s.b,s.j,len(s.uv)))
        for x,(u,v) in sorted(s.uv.items()):raw.extend(CELL.pack(x,u,v))
        for j in s.offsets:raw.extend(PTR.pack(j))
    cost=dict(build_events=len(selected),build_members=members,build_updates=updates,
              cells=sum(len(s.uv) for s in strata.values()),
              nonzero_counts=sum(int(u>0)+int(v>0) for s in strata.values() for u,v in s.uv.values()),
              headers=len(strata),joint_events=sum(len(s.offsets) for s in strata.values()),
              joint_members=sum(m*len(s.offsets) for m,s in strata.items()),packet_bytes=len(raw))
    return bytes(raw),cost

def unpack(raw):
    pos=1;strata={}
    for _ in range(raw[0]):
        m,a,b,j,n=HEADER.unpack_from(raw,pos);pos+=HEADER.size
        s=Stratum(a,b,j)
        for _ in range(n):
            x,u,v=CELL.unpack_from(raw,pos);pos+=CELL.size;s.uv[x]=(u,v)
        if m>2:
            for _ in range(j):
                address,=PTR.unpack_from(raw,pos);pos+=PTR.size;s.offsets.append(address)
        strata[m]=s
    assert pos==len(raw)
    return strata

def bounds(m,s,tighten):
    lo={x:max(0,u-s.a,v-s.b) if m>2 else 0 for x,(u,v) in s.uv.items()}
    hi={x:min(u,v,s.j) if m>2 else 0 for x,(u,v) in s.uv.items()}
    total=s.j*(m-2)
    if tighten:
        while True:
            sum_lo,sum_hi=sum(lo.values()),sum(hi.values())
            assert sum_lo<=total<=sum_hi
            changed=False
            for x in lo:
                low=max(lo[x],total-(sum_hi-hi[x]));high=min(hi[x],total-(sum_lo-lo[x]))
                assert lo[x]<=low<=high<=hi[x]
                changed|=lo[x]!=low or hi[x]!=high
                lo[x],hi[x]=low,high
            if not changed:break
    step=UNIT//(m-2) if m>2 else 0
    return {x:(lo[x]*step,hi[x]*step) for x in lo}

def rank_interval(maps,combined,total,recent):
    q_low=Counter();q_hi=Counter()
    for limits in maps.values():
        for x,(lo,hi) in limits.items():
            q_low[x]+=lo;q_hi[x]+=hi
    left={x:(p*UNIT+total*q_low[x],p,recent[x],-x) for x,p in combined.items()}
    right={x:(p*UNIT+total*q_hi[x],p,recent[x],-x) for x,p in combined.items()}
    order=sorted(combined,key=left.get,reverse=True)
    k=min(8,len(order));leaders=order[:k]
    # A prefix is certified only if each selected path beats every subsequent path in order.
    highest=None;ids=True
    for i in range(len(order)-1,-1,-1):
        x=order[i]
        if i<k and highest is not None and left[x]<=highest:ids=False
        if highest is None or right[x]>highest:highest=right[x]
    exact=ids and all(left[x][0]==right[x][0] for x in leaders)
    possible=set(leaders)
    if leaders:possible.update(x for x in order[k:] if right[x]>left[leaders[-1]])
    return leaders,left,possible,ids,exact

def certify(raw,freq,fallback,fetch):
    strata=unpack(raw)
    combined=Counter({x:0 for x in fallback})
    for m,s in strata.items():
        for x,(u,v) in s.uv.items():combined[x]+=(u+v)*(UNIT//(m-1))
    total=sum(combined.values())
    plain={m:bounds(m,s,False) for m,s in strata.items()}
    _,_,_,plain_ids,plain_scores=rank_interval(plain,combined,total,freq)
    maps={m:bounds(m,s,True) for m,s in strata.items()}
    visits=[];members=reads=0;first_ids=None
    while True:
        leaders,left,contenders,ids,scores=rank_interval(maps,combined,total,freq)
        if not visits:initial_ids,initial_scores=ids,scores
        if ids and first_ids is None:first_ids=[reads,members]
        if scores:
            ranked=[(x,Fraction(left[x][0],total*UNIT) if total else Fraction(0)) for x in leaders]
            return ranked,dict(plain_ids=plain_ids,plain_scores=plain_scores,initial_ids=initial_ids,
                               initial_scores=initial_scores,reads=reads,members=members,ids_reads=first_ids[0],
                               ids_members=first_ids[1],opened=visits)
        candidates=[]
        for m,limits in maps.items():
            width=sum(hi-lo for x,(lo,hi) in limits.items() if x in contenders)
            if width:
                size=m*len(strata[m].offsets)
                assert size>0
                candidates.append((Fraction(width,size),-size,-m,m))
        assert candidates
        m=max(candidates)[-1];s=strata[m]
        observations=Counter()
        for j in s.offsets:
            e=fetch(j)
            assert len(e)==m
            observations.update(x for x in e if x in s.uv)
        step=UNIT//(m-2)
        for x,(lo,hi) in maps[m].items():
            true=observations[x]*step
            assert lo<=true<=hi
            maps[m][x]=(true,true)
        reads+=len(s.offsets);members+=m*len(s.offsets);visits.append(m)
