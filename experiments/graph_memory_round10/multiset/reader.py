"""Payload-only single-query decoder: accepts bytes and changed symbol strings."""
import hashlib,struct,zlib

def hash_lanes(seed,family,key):
    return struct.unpack('<8I',hashlib.blake2b(key.encode(),digest_size=32,person=b'R9matrix',salt=struct.pack('<II',seed,family)).digest())
def xor_lanes(seed,retry,key):
    return struct.unpack('<4I',hashlib.blake2b(key.encode(),digest_size=16,person=b'R10xormap',salt=struct.pack('<II',seed,retry)).digest())
def bits(raw,index,w):
    offset=index*w
    j=offset//8
    return (int.from_bytes(raw[j:j+(w+14)//8],'little')>>(offset%8))&((1<<w)-1)
def r9_read(data,n,seed,queries):
    tag=data[0]
    if tag==2:
        start=1+3*(n+1)
        pairs=list(struct.iter_unpack('<HB',data[1:start]))
    else:
        start=1+(n if tag==1 else 0); available=len(data)-start
        pairs=[(available//n+int(i<available%n),data[1+i] if tag==1 else 4) for i in range(n)]
    masks=0; lanes={f:[hash_lanes(seed,f,q) for q in queries] for f in range(2 if tag==2 else 1)}
    for i,(size,k) in enumerate(pairs):
        buf=data[start:start+size];start+=size
        if not size or not k:continue
        family=int(tag==2 and i==0)
        for hs in lanes[family]:
            if all(buf[(h%(size*8))//8] & (1<<((h%(size*8))%8)) for h in hs[:k]):
                if family:return (1<<n)-1
                masks|=1<<(i-int(tag==2));break
    assert start==len(data)
    return masks
def read(data,queries):
    tag,n,seed=data[:3]
    if tag==0:return r9_read(data[3:],n,seed,queries)
    full=(1<<n)-1
    if tag==1:
        k=data[3];raw=memoryview(data)[4:];m=len(raw)*8//n
        out=0
        for q in queries:
            mask=full
            for x in hash_lanes(seed,0,q)[:k]:mask&=bits(raw,x%m,n)
            out|=mask
        return out
    if tag==2:
        m,count=struct.unpack_from('<IH',data,3); width=(n+7)//8; pos=9
        classes=[int.from_bytes(data[pos+i*width:pos+(i+1)*width],'little') for i in range(count)]
        pos+=width*count; packed=zlib.decompress(data[pos:]); indexw=1 if count<=256 else 2
        assert len(packed)==m*indexw
        out=0
        for q in queries:
            i=hash_lanes(seed,0,q)[0]%m; v=int.from_bytes(packed[i*indexw:(i+1)*indexw],'little')
            out|=classes[v]
        return out
    if tag==3:
        length,w,retry,count=struct.unpack_from('<HBBH',data,3)
        width=(n+7)//8; pos=9
        classes=[int.from_bytes(data[pos+i*width:pos+(i+1)*width],'little') for i in range(count)]
        raw=memoryview(data)[pos+count*width:]
        out=0;w_mask=(1<<w)-1
        for q in queries:
            a,b,c,v=xor_lanes(seed,retry,q)
            code=(v&w_mask)^bits(raw,a%length,w)^bits(raw,length+b%length,w)^bits(raw,2*length+c%length,w)
            if code<count:out|=classes[code]
        return out
    raise ValueError(f'Unknown representation {tag}')
