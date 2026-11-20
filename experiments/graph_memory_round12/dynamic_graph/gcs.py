"""Small paid per-row Golomb-coded membership filters."""
import base64,struct
from util12 import D,load,dump,sha
from reader import hash_lanes
from write import frames,chunks,SEEDS,BS
from store12 import H,parts,pad
def codestream(hashes,n,p):
    domain=n*(1<<p)
    sortedvals=sorted((h*domain)>>32 for h in hashes);mask=(1<<p)-1
    code=0;at=0;before=0
    for val in sortedvals:
        gap=val-before;before=val;q=gap>>p
        code|=((1<<q)-1)<<at;at+=q+1
        code|=(gap&mask)<<at;at+=p
    return code.to_bytes((at+7)//8,'little')
def block(words,seed,size):
    n=len(words)
    if not n:return bytes(size)
    hs=[hash_lanes(seed,0,w)[0] for w in words]
    for p in range(min(23,(size-3)*8//n),-1,-1):
        stream=codestream(hs,n,p)
        if 3+len(stream)<=size:return pad(struct.pack('<HB',n,p)+stream,size)
    return pad(struct.pack('<HB',0xffff,0),size)
def decode_block(raw):
    n,p=struct.unpack_from('<HB',raw)
    if n==65535:return None,None
    if not n:return 0,set()
    stream=int.from_bytes(raw[3:],'little');mask=(1<<p)-1;acc=0;members=set()
    for _ in range(n):
        zero=~stream&(stream+1);q=zero.bit_length()-1
        stream>>=q+1;acc+=(q<<p)|(stream&mask);stream>>=p;members.add(acc)
    return n*(1<<p),members
def lookup(raw):
    n,s,act=raw[1:4];groups=parts(H,len(raw)-H,n)
    decoded=[decode_block(raw[a:b]) for a,b in groups]
    def get(word):
        h=hash_lanes(s,0,word)[0]
        return sum(1<<i for i,(limit,ids) in enumerate(decoded) if ids is None or (h*limit)>>32 in ids)&act
    return get
def refresh(raw,r,words):
    n,s,act=raw[1:4];a,b=parts(H,len(raw)-H,n)[r]
    new=bytearray(raw);new[3]|=1<<r;new[a:b]=block(words,s,b-a)
    return bytes(new),[(a,b)]+([] if new[3]==act else [(0,H)])
def main():
    for p in sorted((D/'events').glob('*.gz')):
        x=load(p);n=x['n'];arch,snaps=frames(x['events'],n);rows=[]
        for b in BS:
            for s in SEEDS:
                for gate in (0,1):
                    raw=bytes([90,n,s,0,0,0,0,0])+bytes(n*b-H)
                    for ev,(offs,_,end) in zip(x['events'],snaps):
                        r=ev['i'];replay=0;same=False
                        if gate and offs[r] is not None:
                            old,replay=chunks(arch,offs[r]);same=(old==ev['words'])
                        if same:rg=[]
                        else:raw,rg=refresh(raw,r,ev['words'])
                        rows.append([ev['step'],ev['phase'],b,s,gate,base64.b64encode(raw).decode(),rg,replay])
        target=D/'gcs_states'/p.name;dump(target,rows)
    files=list((D/'gcs_states').glob('*.gz'))+[D/'gcs.py',D/'GCS_PROTOCOL.md']
    dump(D/'gcs_seal.json',{p.relative_to(D).as_posix():sha(p) for p in files})
if __name__=='__main__':main()