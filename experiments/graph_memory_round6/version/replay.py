import argparse
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

import version_policy as method
from version_policy import HERE, WORK, AP, old, ARMS

R5=AP.parent
TRANSFER=R5/'action_transfer'
EXTERNAL=HERE/'external'
PANELS=('probe','transfer','external')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locks(files):
    return {os.path.relpath(f,HERE).replace('\\','/'):digest(f) for f in sorted(set(files))}


def save(name,data):
    (HERE/name).write_text(json.dumps(data,ensure_ascii=True,indent=1),encoding='utf8')


def check(file,key='files'):
    for f,h in json.loads((HERE/file).read_bytes())[key].items():
        assert digest(HERE/f)==h, f


def inputs(panel,k):
    if panel=='probe':
        return R5/'writer'/f'source_{k}.jsonl.gz',AP/'raw_pairs.jsonl.gz'
    if panel=='transfer':
        return TRANSFER/f'source_{k}.gz',TRANSFER/f'terminal_{k}.gz'
    return EXTERNAL/'source.gz',EXTERNAL/'terminal.gz'


def jobs():
    return [(p,k) for p in PANELS for k in range(1 if p=='external' else 8)]


def freeze():
    assert not (HERE/'method_lock.json').exists()
    src=[HERE/f for f in ('version_policy.py','replay.py','score.py','PROTOCOL_RU.md','acquire_external.py')]
    src += [Path(m.__file__) for m in tuple(sys.modules.values()) if getattr(m,'__file__',None) and str(WORK).lower() in str(m.__file__).lower() and str(m.__file__).endswith('.py')]
    src += [old.memory.D/'python_prior.bin',old.memory.D/'risk_model.json',old.prior.R2/'edit_memory/model.json',old.prior.R2/'span_memory/width_model.json',old.prior.R2/'span_memory/offset.json',EXTERNAL/'sources_lock.json',EXTERNAL/'roster_lock.json']
    for p,k in jobs():
        src.extend(inputs(p,k))
        if p!='external':
            src.append((AP if p=='probe' else TRANSFER)/f'bounded_steps_{k}.gz')
    save('method_lock.json',dict(utc=old.stamp(),python=sys.version,files=locks(src)))


def run(job):
    panel,k=job
    src,pairs=inputs(panel,k)
    raw=dict(old.rr(pairs))
    previous=iter(old.rr((AP if panel=='probe' else TRANSFER)/f'bounded_steps_{k}.gz')) if panel!='external' else None
    old.memory.pack=lambda s,_:old.encode(s,'zstd15','json')
    old.memory.unpack=lambda b,_:old.decode(b)
    weights=old.anchor.weights()
    with gzip.open(HERE/f'states_{panel}_{k}.gz','wt',encoding='utf8',compresslevel=2) as out:
        for q in old.rr(src):
            iid=q['instance']
            immutable={j:q[j] for j in ('instance','issue')}
            rules={a:('dict_lru' if a=='lru' else 'cal_neighbor') for a in ARMS}
            blobs={a:b'\x01'+old.memory.initial(rules[a]) for a in ARMS}
            for t,(event,extra) in enumerate(zip(q['events'],raw[iid],strict=True),1):
                snap={};cost={}
                for arm in ARMS:
                    stats=collections.Counter()
                    start=time.process_time_ns()
                    root=bool(blobs[arm][0])
                    reads=old.pol.readlines(extra,root)
                    writes=method.mutations(extra,root) if arm in ('invalidate','transport') else []
                    root=method.next_root(root,extra)
                    def transition(s,m,e,j):
                        method.advance(s,m,e,j,reads,writes,arm,stats)
                    old.prior.advance=transition
                    blob,fit=old.memory.transition(rules[arm],blobs[arm][1:],event,immutable,weights,4095)
                    blobs[arm]=bytes([int(root)])+blob
                    cpu=time.process_time_ns()-start
                    assert len(blobs[arm])==fit[1]+1<=4096
                    snap[arm]=base64.b64encode(blobs[arm]).decode()
                    cost[arm]=[cpu,len(blobs[arm]),dict(stats)]
                if previous is not None:
                    expected_id,expected_step,hashes=next(previous)
                    assert (iid,t)==(expected_id,expected_step)
                    for arm,ref in [('r5','address'),('lru','lru_address')]:
                        assert [len(blobs[arm]),hashlib.sha256(blobs[arm]).hexdigest()]==hashes[ref],(iid,t,arm)
                old.write(out,[iid,t,snap,cost])
    assert previous is None or next(previous,None) is None
    return job


def predict():
    assert not (HERE/'state_lock.json').exists()
    check('method_lock.json')
    with concurrent.futures.ProcessPoolExecutor(3) as pool:
        for done in pool.map(run,jobs()): print('sealed shard',*done,flush=True)
    fs=[HERE/f'states_{p}_{k}.gz' for p,k in jobs()]
    save('state_lock.json',dict(utc=old.stamp(),method_sha=digest(HERE/'method_lock.json'),files=locks(fs)))


if __name__=='__main__':
    action=argparse.ArgumentParser()
    action.add_argument('mode',choices=['freeze','predict'])
    if action.parse_args().mode=='freeze': freeze()
    else: predict()
