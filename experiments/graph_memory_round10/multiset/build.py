"""Blind write phase. Inputs are old symbol sets, never change keys or outcomes."""
import base64
from concurrent.futures import ProcessPoolExecutor
import os,sys,time
import numpy as np
from common import ROOT,R9,ARMS,put,load,sha,locks
from structures import flat,sparse,xormap
sys.path.append(str(R9/'budget'))
import sketch
def build_case(path):
    d=load(path);ss=[set(s) for s in d['sets']];n=len(ss)
    start=time.process_time_ns()
    masks={}
    for i,words in enumerate(ss):
        for s in words:masks[s]=masks.get(s,0)|(1<<i)
    keys=sorted(masks); values=np.array([masks[k] for k in keys],dtype=np.uint16)
    common_ns=time.process_time_ns()-start
    card=list(map(len,ss));allstates=[]
    for cap0 in [64,256]:
        cap=cap0*n
        for seed in range(32):
            stash={}
            for method in ARMS:
                start=time.process_time_ns()
                if method=='r9':
                    sketch.addresses.cache_clear()
                    plan=sketch.layout(ss,cap-3)['selected']
                    inner=sketch.encoded(plan,seed)
                    state=bytes([0,n,seed])+inner
                    meta={'type':'r9_'+str(plan[1]),'risk':plan[0],'used':len(state)}
                    sketch.addresses.cache_clear()
                elif method=='bucket':
                    state,meta=flat(n,seed,cap,keys,values,card,1)
                elif method=='flat_bloofi':
                    state,meta=flat(n,seed,cap,keys,values,card)
                elif method=='sparse_dict':
                    state,meta=sparse(n,seed,cap,keys,values,card)
                elif method=='xor_map':
                    state,meta=xormap(n,seed,cap,keys,values,card)
                else:
                    selected=min(['sparse_dict','xor_map'],key=lambda m:(stash[m][1]['risk'],stash[m][1]['used']))
                    state,metadata,_=stash[selected];meta=dict(metadata,selected=selected)
                ns=time.process_time_ns()-start
                if method=='old_selector':ns+=sum(stash[m][2] for m in ['sparse_dict','xor_map'])
                assert len(state)==cap and state[1:3]==bytes([n,seed])
                stash[method]=(state,meta,ns)
                allstates.append({'arm':method,'b':cap0,'salt':seed,'cpu_write_ns':ns,'parameters':meta,'data':base64.b64encode(state).decode()})
    case={k:d[k] for k in ['panel','issue','direction']}
    case.update(n=n,n_symbols=len(keys),n_distinct_masks=len(set(masks.values())),roster_bytes=len(__import__('json').dumps(d['nodes'],separators=(',',':'),ensure_ascii=False).encode()),common_build_ns=common_ns,states=allstates)
    target=ROOT/'states'/d['panel']/path.name
    put(target,case)
    return d['issue'],d['direction']
def main():
    paths=sorted((ROOT/'old').rglob('*.json.gz'))
    assert len(paths)==36 and not (ROOT/'state_seal.json').exists()
    out=ROOT/'states'
    with ProcessPoolExecutor(max_workers=3) as pool:
        todo=[p for p in paths if not (out/p.parent.name/p.name).exists()]
        for ans in pool.map(build_case,todo,chunksize=1):print(*ans,flush=True)
    locked=[ROOT/n for n in ['PROTOCOL.md','prepare.py','build.py','reader.py','structures.py','common.py','query.py','grade.py','input_receipt.json']]
    locked+=paths+list(out.rglob('*.json.gz'))
    assert len(list(out.rglob('*.json.gz')))==36
    put(ROOT/'state_seal.json',{'local':locks(locked),'upstream':{str(R9/'budget'/'sketch.py'):sha(R9/'budget'/'sketch.py')}})
if __name__=='__main__':main()
