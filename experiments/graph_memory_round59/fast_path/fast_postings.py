"""Append to complete posting packets and probe canonical varints without decoding bodies."""
from functools import reduce
from itertools import accumulate
from operator import xor
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"reconcile"))
from summary_cache import ABS,DELTA,BITS,NUM,XOR,POST,EVENT,SketchPolicy,unpack,varints,append


def first(payload):
    end=next(i+1 for i,n in enumerate(payload) if n<128)
    value,=unpack(payload[:end])
    return value,end


def build(ids,delta_only=False):
    absolute=bytes([ABS])+varints(ids)
    if not ids:return bytes([DELTA,0]) if delta_only else absolute
    gaps=varints(j-k-1 for j,k in zip(ids,(-1,*ids[:-1])))
    delta=bytes([DELTA])+varints((ids[-1]+1,))+gaps
    if delta_only:return delta
    layouts=[absolute,delta]
    width=(ids[-1]-ids[0])//8+1
    if width<len(min(layouts,key=len)):
        bit=bytearray(width)
        for j in ids:
            n=j-ids[0];bit[n//8]|=1<<(n%8)
        layouts.append(bytes([BITS])+varints((ids[0],))+bit)
    return min(layouts,key=len)


def unpack_full(blob):
    tag=blob[0];body=blob[1:]
    if tag==ABS:return unpack(body)
    base,n=first(body)
    if tag==DELTA:
        vals=tuple(i-1 for i in accumulate(g+1 for g in unpack(body[n:])))
        assert base==(vals[-1]+1 if vals else 0)
        return vals
    if tag!=BITS:raise ValueError("expected complete list")
    return tuple(base+8*p+j for p,b in enumerate(body[n:]) for j in range(8) if b>>j&1)


def add(blob,j):
    tag=blob[0]
    if tag>=NUM:return append(blob,j)
    if tag==ABS:return blob+varints((j,))
    base,n=first(blob[1:])
    if tag==DELTA:
        return bytes([DELTA])+varints((j+1,))+blob[n+1:]+varints((j-base,))
    offset=j-base
    bits=bytearray(blob)
    index=n+1+offset//8
    bits.extend(bytes(max(0,index+1-len(bits))))
    bits[index]|=1<<(offset%8)
    return bytes(bits)


def contains(data,needle):
    offset=data.find(needle)
    while offset>=0:
        if not offset or data[offset-1]<128:return True
        offset=data.find(needle,offset+1)
    return False


class Fast(SketchPolicy):
    def __init__(self,store,hot,mode,budget):
        super().__init__(store,hot,XOR if mode.startswith("xor") else None,budget)
        self.mode=mode

    def expand(self,packet):
        return unpack_full(packet)

    def after_write(self,j,fs):
        for f in fs:
            key=(POST,f)
            data=self.cache.items.get(key)
            if data is not None:
                self.cache.put(key,add(data,j),refresh=False)
                self.cache.updates+=1

    def admit(self,f,ids,record,stats):
        exact=build(ids,self.mode=="delta")
        if self.kind is None:return exact
        short=bytes([XOR])+varints((len(ids),reduce(xor,ids,0)))
        return short if len(short)<len(exact) else exact

    def resident(self,f,hot,stats):
        if self.mode!="xor_native":
            return super().resident(f,hot,stats)
        present=set(hot)
        if f<0:
            return present
        needle=varints((f,))
        scanned=size=0
        for (tag,j),data in self.cache.items.items():
            if tag==EVENT:
                scanned+=1;size+=len(data)
                if contains(data,needle):present.add(j)
        stats["scan_objects"]+=scanned
        stats["scan_bytes"]+=size
        return present
