import base64,struct
from util12 import D,load,dump,sha
from patches import encode_patch
from gcs import block,decode_block
from store12 import H,parts,bloom,bloom_get
from reader import hash_lanes
from write import SEEDS,BS
MODES=['fixed_bloom','fixed_gcs','risk','stable']
def options(old,words,s,mode):
    n=len(old)
    if mode!='fixed_gcs':
        b=bloom(words,n-1,s);m=(n-2)*8;k=b[0]
        if k:rb=(sum(v.bit_count() for v in b[1:])/m)**k
        else:rb=0
        bb=b'\x01'+b;choices=[(rb,len(encode_patch(old,bb)[0]),1,bb)]
    else:choices=[]
    if mode!='fixed_bloom':
        g=block(words,s,n-1);space,keys=decode_block(g)
        rg=1. if keys is None else len(keys)/space if space else 0.
        gg=b'\x02'+g;choices.append((rg,len(encode_patch(old,gg)[0]),2,gg))
    if mode=='stable':
        ok=[c for c in choices if c[0]<=.01]
        if ok:return min(ok,key=lambda c:(c[1],c[0],c[2]))
    return min(choices,key=lambda c:(c[0],c[1],c[2]))
def upd(raw,i,words,mode):
    n,s,active=raw[1:4];a,b=parts(H,len(raw)-H,n)[i]
    prev=raw[a:b];risk,patch,tag,body=options(prev,words,s,mode)
    out=bytearray(raw);out[a:b]=body;out[3]|=1<<i
    return bytes(out),dict(tag=tag,rate=risk,change=int(prev[0] not in (0,tag)),slot_patch=patch)
def decode(raw):
    n,s,active=raw[1:4];layout=[]
    for a,b in parts(H,len(raw)-H,n):
        tag=raw[a];slot=raw[a+1:b];layout.append((tag,decode_block(slot) if tag==2 else slot))
    def get(term):
        hs=hash_lanes(s,0,term);out=0
        for i,(tag,buf) in enumerate(layout):
            if tag==1 and bloom_get(buf,hs):out|=1<<i
            if tag==2:
                space,keys=buf
                if keys is None or ((hs[0]*space)>>32) in keys:out|=1<<i
        return out&active
    return get
def main():
    for p in sorted((D/'events').glob('*.gz')):
        e=load(p);n=e['n'];rows=[]
        for b in BS:
            for s in SEEDS:
                for mode in MODES:
                    raw=bytes([91,n,s,0,0,0,0,0])+bytes(n*b-H)
                    for ev in e['events']:
                        raw,meta=upd(raw,ev['i'],ev['words'],mode)
                        rows.append([ev['step'],ev['phase'],b,s,mode,base64.b64encode(raw).decode(),meta])
        dump(D/'adaptive_states'/p.name,rows)
    files=list((D/'adaptive_states').glob('*.gz'))+[D/'adaptive.py',D/'ADAPTIVE_PROTOCOL.md',D/'patches.py',D/'gcs.py']
    dump(D/'adaptive_seal.json',{p.relative_to(D).as_posix():sha(p) for p in files})
if __name__=='__main__':main()