"""Fully encoded old symbol graph; supplementary scale control, no query or gold input."""
import base64,lzma,zlib
from collections import Counter
from qutil import Q,R10,load,put,sha
from exact import varint,getint
def encode(dist,n,front):
    data=bytearray(varint(len(dist)));prev=b''
    for key,mask in sorted(dist.items()):
        k=key.encode()
        if front:
            shared=0
            while shared<len(k) and shared<len(prev) and k[shared]==prev[shared]:shared+=1
            data+=varint(shared);end=k[shared:]
        else:end=k
        data+=varint(len(end))+end+mask.to_bytes((n+7)//8,'little');prev=k
    return bytes(data)
def restore(buf):
    tag,n,_=buf[:3];flag=tag//3;compression=tag%3
    raw=(lambda v:v,zlib.decompress,lzma.decompress)[compression](buf[3:])
    size,pos=getint(raw,0);result={};prev=b'';width=(n+7)//8
    for _ in range(size):
        shared,pos=getint(raw,pos) if flag else (0,pos)
        length,pos=getint(raw,pos);key=prev[:shared]+raw[pos:pos+length];pos+=length
        m=int.from_bytes(raw[pos:pos+width],'little');pos+=width;result[key.decode()]=m;prev=key
    assert pos==len(raw)
    return result
def main():
    rows=[];states=[];locks={}
    for p in sorted((R10/'old').rglob('*.gz')):
        old=load(p);ss=old['sets'];dist={};n=len(ss)
        for i,words in enumerate(ss):
            for w in words:dist[w]=dist.get(w,0)|(1<<i)
        candidates=[]
        for front in (0,1):
            raw=encode(dist,n,front)
            for comp,encoded in enumerate([raw,zlib.compress(raw,9),lzma.compress(raw,format=lzma.FORMAT_ALONE,preset=6)]):
                data=bytes([front*3+comp,n,0])+encoded
                assert restore(data)==dist
                candidates.append(data)
        chosen=min(candidates,key=len)
        rows.append(dict(task=old['issue'],direction=old['direction'],n=n,keys=len(dist),bytes=len(chosen),per_test=len(chosen)/n,all_sizes=list(map(len,candidates)),layout=chosen[0]))
        states.append([old['issue'],old['direction'],base64.b64encode(chosen).decode()]);locks[str(p.relative_to(R10))]=sha(p)
    put(Q/'sympy_full.json',dict(rows=rows,snapshots=len(rows),fit={b:sum(r['bytes']<=b*r['n'] for r in rows) for b in [16,64,256]},source_locks=locks));put(Q/'sympy_full_states.json.gz',states)
if __name__=='__main__':main()