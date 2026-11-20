"""Standalone Elias--Fano decoder. State + symbol strings suffice."""
import bisect,struct,zlib
from reader import hash_lanes,bits,read

def decode(data):
    if data[0]!=4:
        return lambda queries:read(data,queries)
    _,n,seed,q,ell,compressed,m,colors=struct.unpack_from('<6B2H',data)
    width=(n+7)//8
    pos=10
    values=[int.from_bytes(data[pos+i*width:pos+(i+1)*width],'little') for i in range(colors)]
    pos+=width*colors
    low=data[pos:pos+(m*ell+7)//8];pos+=len(low)
    nb=(((1<<q)-1)>>ell)+m
    high=data[pos:pos+(nb+7)//8];pos+=len(high)
    codes=zlib.decompress(data[pos:]) if compressed else data[pos:]
    cw=max(1,(colors-1).bit_length())
    addresses=[];masks=[]
    for j,byte in enumerate(high):
        while byte:
            off=(byte&-byte).bit_length()-1
            i=len(addresses)
            addresses.append(((8*j+off-i)<<ell)|(bits(low,i,ell) if ell else 0))
            masks.append(values[bits(codes,i,cw)])
            byte&=byte-1
    assert len(addresses)==m
    def lookup(queries):
        total=0
        for word in queries:
            h=hash_lanes(seed,0,word)[0]&((1<<q)-1)
            i=bisect.bisect_left(addresses,h)
            if i<m and addresses[i]==h:total|=masks[i]
        return total
    return lookup