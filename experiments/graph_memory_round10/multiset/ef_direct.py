"""Direct payload lookup by select-zero on the unary high bits; no materialized key array."""
import struct,zlib
from reader import bits,hash_lanes,read
def lookup(raw,queries):
    if raw[0]!=4:return read(raw,queries)
    _,n,seed,q,ell,compressed,m,colors=struct.unpack_from('<6B2H',raw)
    width=(n+7)//8;cw=max(1,(colors-1).bit_length());mask=(1<<q)-1
    nlow=(m*ell+7)//8;nb=(mask>>ell)+m
    off=10+width*colors;low=memoryview(raw)[off:off+nlow]
    start=off+nlow;end=start+(nb+7)//8
    highs=int.from_bytes(raw[start:end],'little')
    codes=zlib.decompress(raw[end:]) if compressed else memoryview(raw)[end:]
    def select_zero(k):
        # First length covering k+1 zeros, minus one, i.e. zero-based bit index.
        a,b=1,nb
        while a<b:
            mid=(a+b)//2
            if mid-(highs&((1<<mid)-1)).bit_count()>=k+1:b=mid
            else:a=mid+1
        return a-1
    out=0
    for key in queries:
        h=hash_lanes(seed,0,key)[0]&mask
        hi=h>>ell;lo=h&((1<<ell)-1)
        pos=0 if hi==0 else select_zero(hi-1)+1
        i=pos-hi
        while pos<nb and ((highs>>pos)&1):
            real=bits(low,i,ell) if ell else 0
            if real==lo:
                j=bits(codes,i,cw);out|=int.from_bytes(raw[10+j*width:10+(j+1)*width],'little');break
            if real>lo:break
            i+=1;pos+=1
    return out