"""Fit exclusively on old line sets. The caller locks states before queries."""
import base64
import numpy as np
from qutil import Q,R9,R10,load,put,sha
from structures import flat,sparse,xormap,pad
from ef_build import build as ef
from exact import layouts
import sketch
METHODS=['r9','bucket','flat_bloofi','sparse_dict','xor_map','old_selector','elias_fano','exact','always']
def prepare(d):
    sets=[set(map(str,v)) for v in d['sets']];dist={}
    for i,words in enumerate(sets):
        for w in words:dist[int(w)]=dist.get(int(w),0)|(1<<i)
    keys=sorted(map(str,dist));masks=np.array([dist[int(k)] for k in keys],np.uint16)
    return sets,dist,keys,masks,list(map(len,sets))
def state(method,b,seed,prep):
    ss,dist,keys,vals,cards=prep;n=len(ss);cap=n*b
    if method=='always':return pad(bytes([7,n,seed]),cap),{'used':3}
    if method=='exact':
        dense,sparsev=layouts(n,seed,dist);v=min([dense,sparsev],key=len)
        meta=dict(used=min(len(v),3) if len(v)>cap else len(v),dense=len(dense),sparse=len(sparsev),exact_fits=len(v)<=cap)
        return pad(v if len(v)<=cap else bytes([7,n,seed]),cap),meta
    if method=='r9':
        sketch.addresses.cache_clear()
        out=bytes([0,n,seed])+sketch.encoded(sketch.layout(ss,cap-3)['selected'],seed)
        sketch.addresses.cache_clear()
        return out,dict(used=len(out))
    args=[n,seed,cap,keys,vals,cards]
    if method=='xor_map':return xormap(*args)
    if method=='elias_fano':return ef(*args)
    if method=='flat_bloofi':return flat(*args)
    if method=='bucket':return flat(*args,1)
    if method=='sparse_dict':return sparse(*args)
    x=sparse(*args);y=xormap(*args)
    return min([x,y],key=lambda z:(z[1]['risk'],z[1]['used']))
def main():
    target=Q/'state_seal.json';assert not target.exists()
    paths=sorted((Q/'old').glob('*.gz'));assert len(paths)==18
    for p in paths:
        d=load(p);o=prepare(d);n=len(o[0]);rows=[]
        for b in [16,64,256]:
            for s in range(32):
                for arm in METHODS:
                    data,meta=state(arm,b,s,o);assert len(data)==b*n
                    rows.append([b,s,arm,base64.b64encode(data).decode(),meta])
        put(Q/'states'/p.name,dict(task=d['task'],direction=d['direction'],n=n,states=rows))
    local=[Q/x for x in ['PROTOCOL.md','qutil.py','exact.py','project.py','qbuild.py','native_inputs.json']]+paths+sorted((Q/'states').glob('*.gz'))
    external=[R10/y for y in ['reader.py','structures.py','ef_build.py','ef_direct.py','common.py']]+[R9/'budget'/'sketch.py']
    put(target,dict(local={str(p.relative_to(Q)):sha(p) for p in local},external={str(p.relative_to(R9.parent)):sha(p) for p in external}))
if __name__=='__main__':main()