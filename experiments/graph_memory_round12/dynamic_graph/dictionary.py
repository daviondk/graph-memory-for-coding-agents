import base64,json,struct,zlib
from util12 import D,load,dump,sha
from write import frames,chunks,pages
def encnum(x):
    b=bytearray()
    while x>=128:b.append((x&127)|128);x>>=7
    b.append(x);return bytes(b)
def getnum(buf,pos):
    val=shift=0
    while True:
        c=buf[pos];pos+=1;val|=(c&127)<<shift
        if c<128:return val,pos
        shift+=7
def envelope(mapping,n,active):
    front=bytearray(encnum(len(mapping)));prev=b''
    for term,m in sorted(mapping.items()):
        key=term.encode();j=0
        while j<min(len(prev),len(key)) and prev[j]==key[j]:j+=1
        suffix=key[j:];front+=encnum(j)+encnum(len(suffix))+suffix+bytes([m]);prev=key
    literal=json.dumps(mapping,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    variants=[]
    for use,raw in enumerate([literal,bytes(front)]):
        for code,e in enumerate([raw,zlib.compress(raw,1),zlib.compress(raw,9)]):
            # body byte length is explicit, including the directory charge for variable size.
            variants.append(bytes([3*use+code,n,active,0])+struct.pack('<H',len(e))+e)
    return min(variants,key=len)
def decode(raw):
    tag,n,active,_=raw[:4]
    if tag==255:return None
    body=raw[6:6+struct.unpack_from('<H',raw,4)[0]]
    if tag%3:body=zlib.decompress(body)
    if tag<3:return json.loads(body)
    length,at=getnum(body,0);out={};prev=b''
    for _ in range(length):
        j,at=getnum(body,at);l,at=getnum(body,at);key=prev[:j]+body[at:at+l];at+=l;m=body[at];at+=1
        out[key.decode()]=m;prev=key
    assert at==len(body);return out
def make(cur,words,r,n,fetch,cap,skip):
    old=decode(cur);active=cur[2];bit=1<<r
    if skip and active&bit:
        if old is not None:same={k for k,v in old.items() if v&bit}==set(words)
        else:same=(fetch(r)==words)
        if same:return cur,0
    if old is None:
        old={}
        for i in range(n):
            if i!=r and active&1<<i:
                for w in fetch(i):old[w]=old.get(w,0)|1<<i
    else:old={w:m&~bit for w,m in old.items() if m&~bit}
    for w in words:old[w]=old.get(w,0)|bit
    raw=envelope(old,n,active|bit)
    if cap is not None and len(raw)>cap:raw=bytes([255,n,active|bit,0,0,0])
    return raw,len(raw)
def main():
    for p in sorted((D/'events').glob('*.gz')):
        x=load(p);n=x['n'];archive,snap=frames(x['events'],n);rows=[]
        for b in [64,256,0]:
            for gate in [0,1]:
                old=envelope({},n,0)
                for ev,(offset,amount,end) in zip(x['events'],snap):
                    reads=[];previous=old
                    def fetch(i):
                        words,l=chunks(archive,offset[i]);reads.append([i,offset[i],l]);return words
                    old,emitted=make(old,ev['words'],ev['i'],n,fetch,n*b if b else None,gate)
                    rows.append([ev['step'],ev['phase'],b,gate,base64.b64encode(old).decode(),reads,dict(bytes=len(old),emitted=emitted,replay=sum(z[2] for z in reads),fit=old[0]!=255,cow=len(previous)+(len(old) if emitted else 0),byte_changes=sum(a!=bb for a,bb in zip(previous,old))+abs(len(previous)-len(old)),pages64=pages([(0,len(old))],64) if emitted else 0,pages4096=4096 if emitted else 0)])
        dump(D/'exact_states'/p.name,rows)
    ps=list((D/'exact_states').glob('*.gz'))+[D/'dictionary.py',D/'EXACT_CONTROL.md'];dump(D/'exact_seal.json',{p.relative_to(D).as_posix():sha(p) for p in ps})
if __name__=='__main__':main()