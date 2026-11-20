import base64
import collections
import concurrent.futures
import gzip
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from packing import HERE,old,select,unpack,candidates
import replay
import version_policy

ARMS=('standard','edges','adaptive')
JOBS=[(p,k) for p in ('probe','transfer','external') for k in range(4 if p=='external' else 8)]


def write(name,obj):
    (HERE/name).write_text(json.dumps(obj,indent=1),encoding='utf8')


def check(name):
    for f,h in json.loads((HERE/name).read_bytes())['files'].items():
        assert replay.digest(HERE/f)==h, f


def lock(name,files):
    write(name,dict(utc=old.stamp(),files={os.path.relpath(f,HERE).replace('\\','/'):replay.digest(f) for f in files}))


def count_rows(state):
    return sum(len(ls) for _,_,rs in state[2] for _,_,ls in rs)


def run(job):
    p,k=job
    sk=k if p!='external' else 0
    src,term=replay.inputs(p,sk)
    raw=dict(old.rr(term))
    prev=iter(old.rr(HERE.parent/f'states_{p}_{sk}.gz'))
    weights=old.anchor.weights()
    old.memory.unpack=lambda b,_:unpack(b)
    with gzip.open(HERE/f'codec_{p}_{k}.gz','wt',encoding='utf8',compresslevel=1) as out:
        for taskidx,task in enumerate(old.rr(src)):
            iid=task['instance']
            if p=='external' and taskidx%4!=k:
                for _ in task['events']:next(prev)
                continue
            static={v:task[v] for v in ('instance','issue')}
            blobs={a:b'\x01'+select(['lru',0,[],[],[]],a) for a in ARMS}
            for t,(ev,extra) in enumerate(zip(task['events'],raw[iid],strict=True),1):
                i,j,ref,_=next(prev);assert (i,j)==(iid,t)
                audit={};res={}
                for arm in ARMS:
                    states={}
                    def pack(state,_):
                        b=select(state,arm)
                        states[b]=state
                        return b
                    old.memory.pack=pack
                    start=time.process_time_ns()
                    root=bool(blobs[arm][0])
                    lines=old.pol.readlines(extra,root)
                    root=version_policy.next_root(root,extra)
                    def ingest(s,m,e,j):
                        version_policy.advance(s,m,e,j,lines,[],'r5',{})
                    old.prior.advance=ingest
                    blob,fit=old.memory.transition('dict_lru',blobs[arm][1:],ev,static,weights,4095)
                    cpu=time.process_time_ns()-start
                    logical=unpack(blob)
                    assert logical==states[blob] and logical[1]==t
                    blobs[arm]=bytes([int(root)])+blob
                    assert len(blobs[arm])==fit[1]+1<=4096
                    typ='binary' if blob.startswith(b'V6') else 'edges' if blob[2]%2 else 'json'
                    audit[arm]=[len(blobs[arm]),count_rows(logical),cpu,typ,fit[0]+1,fit[2]]
                    if arm=='standard':
                        sizes=[1+len(v) for v in candidates(logical)]
                        assert sizes[0]==len(blobs[arm])
                        audit[arm].append(sizes)
                    res[arm]=base64.b64encode(blobs[arm]).decode('ascii')
                assert res['standard']==ref['lru']
                old.write(out,[iid,t,res,audit])
    assert next(prev,None) is None
    return job


def main():
    assert not (HERE/'state_lock.json').exists()
    replay.check('method_lock.json');replay.check('dependency_lock.json');replay.check('state_lock.json')
    fs=[HERE/f for f in ('PROTOCOL_RU.md','run_codec.py','packing.py','score_codec.py')]
    fs += [HERE.parent/f for f in ['method_lock.json','dependency_lock.json','state_lock.json','evaluation_lock.json']]
    lock('method_lock.json',fs)
    with concurrent.futures.ProcessPoolExecutor(4) as pool:
        for x in pool.map(run,JOBS):print('sealed',*x,flush=True)
    lock('state_lock.json',[HERE/f'codec_{p}_{k}.gz' for p,k in JOBS]+[HERE/'method_lock.json'])


if __name__=='__main__': main()
