"""Fixed envelopes; reads use only the serialized bytes and query key."""
import functools,hashlib,json,math,struct,zlib
import numpy as np
from util12 import event_raw
from reader import read as xor_read,hash_lanes
from structures import xormap
ARMS=['global_xor','column_bloom','pair_xor','quad_xor','shadow2','batch4','edge_delta','exact_dict','exact_forward']
H=8
def pad(raw,length):
    assert len(raw)<=length
    return raw+bytes(length-len(raw))
def parts(offset,size,count):
    cuts=[offset+i*size//count for i in range(count+1)]
    return list(zip(cuts,cuts[1:]))
def layout(arm,cap,n):
    size=cap-H
    if arm in ('column_bloom','exact_forward'):return parts(H,size,n)
    if arm in ('pair_xor','quad_xor'):
        width=2 if arm=='pair_xor' else 4
        return parts(H,size,(n+width-1)//width)
    if arm=='shadow2':
        loglen=size*3//10
        return [(H,cap-loglen)]+parts(cap-loglen,loglen,2)
    if arm=='edge_delta':
        sep=cap-size*3//10
        return [(H,sep),(sep,cap)]
    return [(H,cap)]
def bloom(words,nbytes,seed):
    if not words:return bytes(nbytes)
    m=(nbytes-1)*8
    k=min(range(1,9),key=lambda i:(1-(1-1/m)**(i*len(words)))**i)
    buf=bytearray(nbytes);buf[0]=k
    for w in words:
        for h in hash_lanes(seed,0,w)[:k]:
            bit=h%m;buf[1+bit//8]|=1<<(bit%8)
    return bytes(buf)
def bloom_get(data,hs):
    k=data[0];m=(len(data)-1)*8
    return bool(k) and all(data[1+(h%m)//8]&(1<<((h%m)%8)) for h in hs[:k])
def xcode(rows,cap,s):
    dist={}
    for i,rr in enumerate(rows):
        for w in rr:dist[w]=dist.get(w,0)|1<<i
    if not dist:return bytes(cap)
    words=sorted(dist);m=np.array([dist[w] for w in words],np.uint16)
    return xormap(len(rows),s,cap,words,m,list(map(len,rows)))[0]
def exactencode(value):
    raw=json.dumps(value,separators=(',',':'),ensure_ascii=False,sort_keys=True).encode()
    return min([b'\x01'+zlib.compress(raw,1),b'\x01'+zlib.compress(raw,9),b'\x02'+struct.pack('<I',len(raw))+raw],key=len)
def exactdecode(raw):
    if raw[0]==0:return {}
    if raw[0]==1:return json.loads(zlib.decompress(raw[1:]))
    if raw[0]==2:return json.loads(bytes(raw[5:5+struct.unpack_from('<I',raw,1)[0]]))
    raise ValueError(raw[0])
def initial(arm,n,b,seed):
    return bytes([ARMS.index(arm),n,seed,0,0,255,255,0])+bytes(n*b-H)
def regions_read(raw):
    buf=memoryview(raw);arm=ARMS[raw[0]];n,s,active,dirty,slot0,slot1,count=raw[1:H]
    bounds=layout(arm,len(raw),n)
    vals=[buf[i:j] for i,j in bounds]
    def x(data,q):return xor_read(data,[q]) if data[0] else 0
    if arm=='exact_dict':
        all_=vals[0][0]==255;mapping={} if all_ else exactdecode(vals[0])
        return lambda q:active if all_ else mapping.get(q,0)&active
    if arm=='exact_forward':
        sets=[None if v[0]==255 else set(exactdecode(v)) for v in vals]
        return lambda q:sum(1<<i for i,v in enumerate(sets) if v is None or q in v)&active
    if arm=='edge_delta':
        delta=exactdecode(vals[1])
        def get(q):
            a,d=delta.get(q,(0,0));return ((x(vals[0],q)&~d)|a)&active
        return get
    if arm=='column_bloom':
        def get(q):
            hs=hash_lanes(s,0,q);return sum(1<<i for i,v in enumerate(vals) if bloom_get(v,hs))&active
        return get
    if arm in ('pair_xor','quad_xor'):
        width=2 if arm=='pair_xor' else 4
        return lambda q:sum(x(v,q)<<(i*width) for i,v in enumerate(vals))&active
    if arm=='shadow2':
        slots=[slot0,slot1]
        def get(q):
            vote=x(vals[0],q);hs=hash_lanes(s,0,q)
            for i,r in enumerate(slots):
                if r<255:
                    vote=vote&~(1<<r)
                    if bloom_get(vals[i+1],hs):vote|=1<<r
            return vote&active
        return get
    if arm=='batch4':return lambda q:(x(vals[0],q)|dirty)&active
    return lambda q:x(vals[0],q)&active
def cold(raw,key):
    return regions_read(raw)(key)
def update(raw,r,words,fetch,skip=False):
    """fetch(i) charges archive bytes per request and returns prior exact row. Current input is free."""
    arm=ARMS[raw[0]];n,s,active,dirty,s0,s1,cnt=raw[1:H];cap=len(raw);bit=1<<r
    bounds=layout(arm,cap,n);writes=[];late=active&bit;oldcache={}
    def prior(i):
        if i not in oldcache:oldcache[i]=fetch(i) if active&(1<<i) else []
        return oldcache[i]
    if skip and late and prior(r)==words:return raw,[],dict(noop=True,compact=False,exact_required=0)
    active2=active|bit;compact=False;required=0
    def rows(l=0,end=None):return [words if i==r else prior(i) for i in range(l,n if end is None else end)]
    def get(j):
        a,b=bounds[j];return memoryview(raw)[a:b]
    def emit(j,buf):
        a,b=bounds[j];writes.append((a,b,pad(buf,b-a)))
    def fit_x(j,rr):emit(j,xcode(rr,len(get(j)),s))
    def exact(j,value):
        nonlocal required
        out=exactencode(value);required=len(out)
        emit(j,out if len(out)<=len(get(j)) else b'\xff')
    if arm=='global_xor':fit_x(0,rows());compact=True
    elif arm=='column_bloom':emit(r,bloom(words,len(get(r)),s))
    elif arm in ('pair_xor','quad_xor'):
        w=2 if arm=='pair_xor' else 4;j=r//w;start=j*w
        fit_x(j,rows(start,min(start+w,n)))
    elif arm=='exact_forward':exact(r,words)
    elif arm=='exact_dict':
        dm={}
        for i,v in enumerate(rows()):
            for key in v:dm[key]=dm.get(key,0)|1<<i
        exact(0,dm);compact=True
    elif arm=='batch4':
        dirty|=bit;cnt+=1
        if cnt==4:fit_x(0,rows());dirty=cnt=0;compact=True
    elif arm=='shadow2':
        slots=[s0,s1]
        if r not in slots and 255 not in slots:
            fit_x(0,rows());slots=[255,255];compact=True
            # Inactive shadow bytes are semantically inaccessible, not wiped.
        else:
            j=slots.index(r) if r in slots else slots.index(255);slots[j]=r
            emit(j+1,bloom(words,len(get(j+1)),s))
        s0,s1=slots
    elif arm=='edge_delta':
        delta=exactdecode(get(1));old=set(prior(r));now=set(words)
        for w in old^now:
            a,d=delta.get(w,[0,0])
            if w in now:a|=bit;d&=~bit
            else:d|=bit;a&=~bit
            delta[w]=[a,d]
        encoded=exactencode(delta)
        if len(encoded)>len(get(1)):
            fit_x(0,rows());emit(1,b'');compact=True
        else:emit(1,encoded)
    head=bytes([raw[0],n,s,active2,dirty,s0,s1,cnt])
    if head!=raw[:H]:writes.append((0,H,head))
    new=bytearray(raw)
    for a,b,v in writes:new[a:b]=v
    return bytes(new),[(a,b) for a,b,v in writes],dict(noop=False,compact=compact,exact_required=required)
