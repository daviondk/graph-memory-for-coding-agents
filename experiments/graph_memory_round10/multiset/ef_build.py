"""Blind construction of a paid, sorted fingerprint dictionary from reference data."""
import base64,struct,zlib
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from common import ROOT,put,load,locks
from reader import hash_lanes
from structures import flat,packed,pad

def build(n,seed,cap,keys,vals,card):
    hashes=np.array([hash_lanes(seed,0,k)[0] for k in keys],np.uint32)
    for q in range(24,3,-1):
        addresses,inv=np.unique(hashes&((1<<q)-1),return_inverse=True)
        m=len(addresses);ell=max(0,((1<<q)//m).bit_length()-1)
        upperbits=(((1<<q)-1)>>ell)+m
        if 10+(upperbits+7)//8+(m*ell+7)//8>cap:continue
        masks=np.zeros(m,np.uint16);np.bitwise_or.at(masks,inv,vals)
        values,codes=np.unique(masks,return_inverse=True)
        colors=len(values);width=(n+7)//8
        if 10+colors*width+(upperbits+7)//8+(m*ell+7)//8>cap:continue
        low=packed(addresses&((1<<ell)-1),ell) if ell else b''
        high=np.zeros(upperbits,dtype=np.uint8)
        high[(addresses>>ell)+np.arange(m)]=1
        rawcodes=packed(codes,max(1,(colors-1).bit_length()))
        zcodes=zlib.compress(rawcodes,1);compressed=len(zcodes)<len(rawcodes)
        raw=struct.pack('<6B2H',4,n,seed,q,ell,compressed,m,colors)
        raw+=values.astype('u1' if width==1 else '<u2').tobytes()+low+np.packbits(high,bitorder='little').tobytes()+(zcodes if compressed else rawcodes)
        if len(raw)<=cap:return pad(raw,cap),{'q':q,'ell':ell,'colors':colors,'m':m,'used':len(raw),'compressed':compressed}
    data,meta=flat(n,seed,cap,keys,vals,card,1)
    return data,dict(meta,q=0)
def transform(d):
    masks={}
    for i,words in enumerate(d['sets']):
        for w in words:masks[w]=masks.get(w,0)|(1<<i)
    keys=sorted(masks);return keys,np.array([masks[k] for k in keys],np.uint16),list(map(len,d['sets']))
def case(path):
    d=load(path);n=len(d['nodes']);keys,vals,card=transform(d);rows=[]
    for b in (64,256):
        for seed in range(32):
            data,meta=build(n,seed,n*b,keys,vals,card)
            assert len(data)==n*b
            rows.append(dict(b=b,salt=seed,arm='elias_fano',data=base64.b64encode(data).decode(),parameters=meta))
    p=ROOT/'ef_states'/d['panel']/path.name
    put(p,dict(panel=d['panel'],issue=d['issue'],direction=d['direction'],n=n,states=rows))
    return p
def main():
    paths=sorted((ROOT/'old').rglob('*.gz'));assert len(paths)==36 and not (ROOT/'ef_seal.json').exists()
    with ProcessPoolExecutor(2) as ex:out=list(ex.map(case,paths))
    put(ROOT/'ef_seal.json',locks([ROOT/p for p in ['ef_build.py','ef_reader.py','ROBUSTNESS_PROTOCOL.md','reader.py','structures.py','common.py']]+paths+out))
if __name__=='__main__':main()