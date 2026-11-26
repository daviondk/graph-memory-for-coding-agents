"""Bounded-precision structural priors and lazy, tie-stable exact prefix selection."""
import heapq
import numpy as np

def nibble(a):
    v=np.asarray(a,dtype=np.uint8)
    if len(v)%2:v=np.append(v,np.uint8(0))
    return (v[::2]|(v[1::2]<<4)).tobytes()

class Index:
    def __init__(self,prior):
        p=np.array(prior,dtype="<f8")
        self.raw=p
        self.bounds=np.linspace(p.min(),p.max(),257)
        codes=np.searchsorted(self.bounds[1:-1],p,side="right").astype(np.uint8)
        self.codes=codes
        self.high=nibble(codes>>4);self.low=nibble(codes&15)
        self.half=p.astype("<f2")
        previous=np.nextafter(self.half,np.float16(-np.inf)).astype(float)
        following=np.nextafter(self.half,np.float16(np.inf)).astype(float)
        self.half_lo=(previous+self.half.astype(float))/2
        self.half_hi=(following+self.half.astype(float))/2
        assert np.all(p>=self.bounds[codes.astype(int)]) and np.all(p<=self.bounds[codes.astype(int)+1])
        assert np.all(p>=self.half_lo) and np.all(p<=self.half_hi)
    def interval(self,mode,order):
        if mode=="fp16":return self.half_lo[order],self.half_hi[order]
        group=self.codes[order].astype(int);step=1 if mode=="b8" else 16
        left=group//step*step;return self.bounds[left],self.bounds[left+step]

def prefix(rank,costs):
    out=[];used=0
    for i in rank:
        used+=int(costs[i])
        if used>2048:break
        out.append(int(i))
    return out

def exact(mode,index,order,signal,costs,get_low,get_raw):
    # Only this interval and the callbacks expose stored data to the decision rule.
    lo,hi=index.interval(mode,order);lower=(signal+lo).tolist();upper=(signal+hi).tolist()
    heap=[(-v,i) for i,v in enumerate(upper)];heapq.heapify(heap)
    state=[0]*len(heap);byte_cache={};output=[];spent=0;raw_reads=0
    while heap:
        bound,i=heapq.heappop(heap)
        if not heap or (-lower[i],i)<=heap[0]:
            spent+=int(costs[order[i]])
            if spent>2048:break
            output.append(int(order[i]))
            continue
        node=int(order[i])
        if mode=="b4_b8" and state[i]==0:
            addr=node//2
            if addr not in byte_cache:byte_cache[addr]=get_low(addr)
            low=(byte_cache[addr]>>(4*(node%2)))&15
            high=(index.high[addr]>>(4*(node%2)))&15
            code=16*high+low
            lower[i]=float(signal[i]+index.bounds[code])
            upper[i]=float(signal[i]+index.bounds[code+1]);state[i]=1
        else:
            assert state[i]!=2
            value=float(signal[i]+get_raw(node));lower[i]=upper[i]=value
            raw_reads+=1;state[i]=2
        heapq.heappush(heap,(-upper[i],i))
    return output,[len(byte_cache),raw_reads]

