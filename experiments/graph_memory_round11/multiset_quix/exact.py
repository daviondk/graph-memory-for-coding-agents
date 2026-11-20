"""Exact packed line-matrix or gap-varint sparse rows, byte-priced intrinsically."""
from reader import bits,read
from ef_direct import lookup
import struct
def varint(value):
    buf=bytearray()
    while value>=128:buf.append((value&127)|128);value>>=7
    buf.append(value)
    return bytes(buf)
def getint(data,pos):
    val=0;shift=0
    while True:
        c=data[pos];pos+=1;val|=(c&127)<<shift;shift+=7
        if c<128:return val,pos
def layouts(n,seed,values):
    high=max(values,default=0);total=0
    for line,mask in values.items():total|=mask<<((line-1)*n)
    dense=bytes([5,n,seed])+varint(high)+total.to_bytes((high*n+7)//8,'little')
    triples=bytearray(bytes([6,n,seed])+varint(len(values)));last=0;width=(n+7)//8
    for line,mask in sorted(values.items()):
        triples+=varint(line-last)+mask.to_bytes(width,'little');last=line
    return (dense,bytes(triples))
def direct(raw,queries):
    tag,n,seed=raw[:3]
    if tag<4:return read(raw,queries)
    if tag==4:return lookup(raw,queries)
    if tag==7:return (1<<n)-1
    words=set(map(int,queries));out=0
    size,pos=getint(raw,3)
    if tag==5:
        buf=memoryview(raw)[pos:]
        for v in words:
            if 1<=v<=size:out|=bits(buf,v-1,n)
    else:
        assert tag==6
        line=0;width=(n+7)//8
        for _ in range(size):
            delta,pos=getint(raw,pos);line+=delta
            if line in words:out|=int.from_bytes(raw[pos:pos+width],'little')
            pos+=width
    return out