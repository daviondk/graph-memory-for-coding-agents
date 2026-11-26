"""Lossless hot/cold decomposition of IEEE binary64 priors, with exact batch refinement."""
import json
import struct
import zlib
import numpy as np
from layers import prefix,exact

def pack(values,dictionary):
    bits=np.array(values,dtype=">f8").view(">u8")
    raw=bits.tobytes();octets=np.frombuffer(raw,dtype="u1").reshape(-1,8)
    heads=(bits>>40).astype(np.uint32);classes,inv=np.unique(heads>>12,return_inverse=True)
    if dictionary and len(classes)<=16:
        keys=((inv.astype(np.uint32)<<12)|(heads&4095)).astype(">u2")
        hot=bytes([len(classes)])+classes.astype(">u2").tobytes()+keys.tobytes()
    else:hot=b"\0"+octets[:,:3].tobytes()
    return hot,octets[:,3:].tobytes()

class Head:
    def __init__(self,hot):
        size=hot[0]
        if size:
            lookup=np.frombuffer(hot,dtype=">u2",count=size,offset=1).astype(np.uint64)
            v=np.frombuffer(hot,dtype=">u2",offset=1+2*size)
            upper=(lookup[v>>12]<<12)|(v&4095)
        else:
            a=np.frombuffer(hot,dtype="u1",offset=1).reshape(-1,3).astype(np.uint64)
            upper=(a[:,0]<<16)|(a[:,1]<<8)|a[:,2]
        self.top=upper.astype("uint64")<<40
        l=self.top.view(np.float64);h=(self.top|((1<<40)-1)).view(np.float64)
        self.lo=np.minimum(l,h);self.hi=np.maximum(l,h)
    def interval(self,_,order):return self.lo[order],self.hi[order]
    def recover(self,node,tail):
        return struct.unpack(">d",(int(self.top[node])|int.from_bytes(tail,"big")).to_bytes(8,"big"))[0]

def batch(head,order,signal,costs,fetch):
    lower=signal+head.lo[order];upper=signal+head.hi[order];mid=(lower+upper)*.5
    ranked=np.argsort(-mid,kind="stable");ordered=order[ranked]
    boundary=int(np.searchsorted(costs[ordered].cumsum(),2048,side="right"))
    future=np.maximum.accumulate(upper[ranked][::-1])[::-1]
    # At ties we conservatively enter the refinement path.
    stop=min(boundary+1,len(ranked)-1)
    if np.all(lower[ranked[:stop]]>future[1:stop+1]):
        return ordered[:boundary].tolist(),0
    by_lower=np.argsort(-lower,kind="stable")
    j=int(np.searchsorted(costs[order[by_lower]].cumsum(),2048,side="right"))
    threshold=lower[by_lower[j]] if j<len(order) else -np.inf
    pool=np.flatnonzero(upper>=threshold)
    by_lo=pool[np.argsort(lower[pool],kind="stable")]
    overlapping=np.zeros(len(by_lo),bool)
    overlapping[1:] |= lower[by_lo[1:]]<=np.maximum.accumulate(upper[by_lo])[:-1]
    overlapping[:-1] |= upper[by_lo[:-1]]>=lower[by_lo[1:]]
    selected=by_lo[overlapping]
    if len(selected):
        ids=order[selected];precise=fetch(ids)
        for i,node in zip(selected,ids):mid[i]=signal[i]+head.recover(node,precise[int(node)])
    tail=pool[np.argsort(-mid[pool],kind="stable")]
    return prefix(order[tail],costs),len(selected)

