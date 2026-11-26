"""Replay the sealed anonymized fixture. No graph packages or source archives required."""
import argparse
import os
import platform
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns as clock
from common44 import D,load,save,sha
from operators import ARMS,apply,connect,flags,END_READ,PAIR_READ,SCAN_READ

def storage(db,path,arm):
    q={'pair':PAIR_READ,'scan':SCAN_READ}.get(arm,END_READ)
    plan=db.execute('EXPLAIN QUERY PLAN '+q,(0,0) if arm=='pair' else (0,)).fetchall()
    assert not any('TEMP B-TREE' in row[-1] for row in plan)
    if arm=='pair':assert any('pair_in' in row[-1] for row in plan)
    wal=path.with_name(path.name+'-wal');wal_bytes=wal.stat().st_size
    start=clock();status=db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone();checkpoint=clock()-start
    assert status==(0,0,0)
    psize=db.execute('PRAGMA page_size').fetchone()[0];pages=db.execute('PRAGMA page_count').fetchone()[0]
    assert psize==4096 and pages*psize==path.stat().st_size
    freelist=db.execute('PRAGMA freelist_count').fetchone()[0]
    objects=db.execute('SELECT name,count(*),sum(pgsize),sum(payload),sum(unused) FROM dbstat GROUP BY name ORDER BY name').fetchall()
    assert sum(row[1] for row in objects)+freelist==pages
    counts={}
    if arm in ('pair','co','scan'):
        counts['pair']=db.execute('SELECT count(*),coalesce(sum(w),0),min(w) FROM pair').fetchone()
        assert counts['pair'][2]>0
    if arm not in ('pair','scan'):
        counts['endpoint']=db.execute('SELECT count(*),sum(nout),sum(nin) FROM endpoint').fetchone()
        assert db.execute('SELECT count(*) FROM endpoint WHERE nout<0 OR nin<0 OR nout+nin=0').fetchone()[0]==0
    return dict(query_plan=plan,wal_before=wal_bytes,checkpoint_ns=checkpoint,page_size=psize,pages=pages,
                free_pages=freelist,objects=objects,file_bytes=pages*psize,counts=counts)

def terminal(path,arm,expected):
    start=clock();db=connect(path,arm,create=False);new_connection=clock()-start
    visits=[]
    for rep in range(2):
        ns=[]
        for t,ref in enumerate(expected):
            start=clock();observed=flags(db,arm,t);ns.append(clock()-start)
            assert observed==ref
        visits.append(ns)
    assert db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
    db.close()
    return new_connection,visits

def run(fixture,rep,reads,out):
    clocks={};info={}
    with TemporaryDirectory(prefix='stage-',dir=out) as tmp:
        paths={arm:Path(tmp)/(arm+'.sqlite') for arm in ARMS};dbs={}
        for arm in ARMS:
            start=clock();dbs[arm]=connect(paths[arm],arm,create=True)
            info[arm]={'setup_ns':clock()-start};clocks[arm]=[]
        last=[]
        for t,frames in enumerate(fixture):
            # Shared oracle construction is excluded from each SQL timer.
            frames=[(d,dict(f)) for d,f in frames];last.append(frames[-1][1])
            rotate=(t+(reads==4))%len(ARMS);order=ARMS[rotate:]+ARMS[:rotate]
            if rep:order=order[::-1]
            for arm in order:
                db=dbs[arm];write=read=validation=0
                for delta,expected in frames:
                    a=clock();apply(db,arm,t,delta);b=clock();write+=b-a
                    for _ in range(reads):
                        a=clock();observed=flags(db,arm,t);b=clock();read+=b-a
                        assert observed==expected
                        validation+=clock()-b
                clocks[arm].append([write,read,validation])
        for arm in ARMS:
            info[arm].update(storage(dbs[arm],paths[arm],arm))
            dbs[arm].close()
            opened,visits=terminal(paths[arm],arm,last)
            info[arm]['reopen_ns']=opened
            for t,(a,b) in enumerate(zip(*visits)):clocks[arm][t].extend((a,b))
            if rep==0 and reads==1 and arm in ('pair','ends','co'):
                os.replace(paths[arm],out/(arm+'.sqlite'))
    return dict(rep=rep,reads=reads,info=info,clocks=clocks)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    out=ap.parse_args().out.resolve();out.mkdir(exist_ok=True,parents=True)
    seal=load(D/'fixture-seal.json')
    assert sha(D/'normalized.json.gz')==seal['fixture']
    fixture=load(D/'normalized.json.gz');assert len(fixture)==1207 and sum(map(len,fixture))==31279
    probes=sqlite3.connect(':memory:');probes.execute('SELECT count(*) FROM dbstat').fetchone()
    opts=[v for v, in probes.execute('PRAGMA compile_options')];probes.close()
    env=dict(sqlite=sqlite3.sqlite_version,python=sys.version,host=platform.platform(),sqlite_options=opts,
        fixture=seal['fixture'],code=sha(D/'operators.py'),runner=sha(D/'replay.py'))
    # All plans share a run. Each run starts with new empty files.
    for rep,schedule in enumerate(((1,4),(4,1))):
        for k in schedule:
            path=out/f'run-{rep}-{k}.json.gz'
            start=clock();record=run(fixture,rep,k,out);record['wall_ns']=clock()-start
            save(path,record);print(rep,k,'seconds',round(record['wall_ns']/1e9,2),flush=True)
    env['records']={p.name:sha(p) for p in sorted(out.glob('run-*.json.gz'))}
    save(out/'run-seal.json',env)

if __name__=='__main__':main()
