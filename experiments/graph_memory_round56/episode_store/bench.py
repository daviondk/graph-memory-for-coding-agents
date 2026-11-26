"""Replay frozen histories in real files, issue pre-update recommendations, measure byte and read budgets."""
import argparse
from collections import Counter,defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import shutil
import sqlite3
import tempfile
from time import perf_counter_ns
from extra_store import EXTRA
from sweep_store import MODES as SWEPT
from store import FIXED,LAYOUTS,connect,initialize,state,top,update

HERE=Path(__file__).resolve().parent
R55=HERE.parents[1]/'graph_memory_round55/cochange'
PANELS={'development':R55,'external':R55/'continuation'}
SEED=56071
BUDGETS=(32,64,128)

def io(path,data=None):
    if data is None:
        raw=path.read_bytes()
        return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)
    raw=(json.dumps(data,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix=='.gz' else raw)

def project(raw):
    ids={}
    previous=defaultdict(list)
    window=[]
    freqs=Counter()
    out=[]
    oracle={}
    for t,(commit,paths) in enumerate(raw['revisions']):
        paths=paths if len(paths)<=64 else []
        query=None
        if t>=64 and len(paths)>=2:
            slot=int(commit,16)%len(paths)
            a=ids.get(paths[slot],-1)
            gold=[ids.get(p,-1) for j,p in enumerate(paths) if j!=slot]
            seq=previous[a]
            def ordered(refs):
                counts=Counter(i for _,peers in refs for i in peers)
                return tuple(sorted((i for i in ids.values() if i!=a),
                                    key=lambda i:(-counts[i],-freqs[i],i))[:8])
            oracle[t]={'full':ordered(seq),'recent':ordered(seq[-8:])}
            query=(a,gold)
        born=[]
        for p in paths:
            if p not in ids:
                ids[p]=len(ids)
                born.append((ids[p],p))
        nodes=tuple(sorted(ids[p] for p in paths))
        for a in nodes:previous[a].append((t,nodes))
        freqs.update(nodes)
        window.append(nodes)
        if len(window)>32:freqs.subtract(window.pop(0))
        out.append((commit,nodes,born,query))
    return out,oracle

def reopen_checks(path,mode,anchors):
    # One connection per query, followed by a same-connection repeat of the identical address.
    first=repeated=opened=0
    for a in anchors:
        start=perf_counter_ns()
        db=connect(path)
        after_open=perf_counter_ns()
        cold_result=top(db,mode,a)
        after_first=perf_counter_ns()
        warm_result=top(db,mode,a)
        end=perf_counter_ns()
        assert warm_result==cold_result
        opened+=after_open-start
        first+=after_first-after_open
        repeated+=end-after_first
        db.close()
    return [opened,first,repeated,len(anchors)]

def execute(path,repo,rows,oracle,mode,budget,serial,save_example):
    db=connect(path)
    initialize(db,mode)
    times=[0,0]
    ranks={}
    for t,(commit,nodes,born,q) in enumerate(rows):
        if q:
            a,gold=q
            start=perf_counter_ns()
            rank=top(db,mode,a)
            times[1]+=perf_counter_ns()-start
            ranks[t]=rank
            if mode in LAYOUTS+EXTRA+SWEPT:
                rule='full' if mode in ('pairs','log','pairblob','undirected','packedlog') else 'recent'
                assert rank==oracle[t][rule],(repo,mode,t)
        start=perf_counter_ns()
        update(db,mode,budget,t,nodes,born)
        times[0]+=perf_counter_ns()-start
    changes=db.total_changes
    tables=state(db,mode)
    if mode in FIXED:
        assert db.execute("SELECT count(*) FROM packet WHERE length(v)!=?",(budget,)).fetchone()[0]==0
        assert tables['node']==tables['packet']
    before=path.stat().st_size
    db.execute('VACUUM')
    after=path.stat().st_size
    assert db.execute('PRAGMA integrity_check').fetchone()==('ok',)
    db.close()
    last=list(dict.fromkeys(q[0] for _,_,_,q in reversed(rows) if q and q[0]>=0))[:20]
    latency=reopen_checks(path,mode,last) if mode in LAYOUTS+EXTRA+SWEPT else []
    if save_example and mode=='intern' and repo=='pallets/flask' and serial==0:
        shutil.copyfile(path,HERE/'example-flask.sqlite')
    return ranks,dict(update_ns=times[0],query_ns=times[1],changed_rows=changes,
                      file_bytes=before,compact_bytes=after,tables=tables,first_warm_ns=latency)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--scratch',type=Path,default=Path('D:/CodexResearch'))
    ap.add_argument('--only',choices=['layout','fixed','all'],default='all')
    ap.add_argument('--blocks',type=int,default=5)
    args=ap.parse_args()
    corp={k:{repo:project(s) for repo,s in io(p/'commits.json.gz').items()} for k,p in PANELS.items()}
    allranks={}
    if args.only in ('fixed','all'):
        schedule=[(k,repo,mode,b) for k,repos in corp.items() for repo in repos for mode in FIXED for b in BUDGETS]
        random.Random(SEED+1).shuffle(schedule)
        data={}
        with tempfile.TemporaryDirectory(dir=args.scratch,prefix='r56-episode-fixed-') as scratch:
            for k,repo,mode,b in schedule:
                path=Path(scratch)/'working.sqlite'
                ranks,measured=execute(path,repo,*corp[k][repo],mode,b,0,False)
                path.unlink()
                data.setdefault(k,{}).setdefault(repo,{})[f'{mode}{b}']=measured
                allranks.setdefault(k,{}).setdefault(repo,{})[f'{mode}{b}']=ranks
        io(HERE/'fixed-measurements.json.gz',data)
        io(HERE/'fixed-ranks.json.gz',allranks)
        print('fixed',len(schedule),flush=True)
    if args.only in ('layout','all'):
        schedule=[(k,repo,mode) for k,repos in corp.items() for repo in repos for mode in LAYOUTS]
        rng=random.Random(SEED)
        blocks=[]
        allranks={}
        with tempfile.TemporaryDirectory(dir=args.scratch,prefix='r56-episode-layout-') as scratch:
            for block in range(args.blocks):
                order=schedule.copy()
                rng.shuffle(order)
                results=[]
                for k,repo,mode in order:
                    path=Path(scratch)/'working.sqlite'
                    ranks,measured=execute(path,repo,*corp[k][repo],mode,0,block,True)
                    path.unlink()
                    part=allranks.setdefault(k,{}).setdefault(repo,{})
                    if mode in part: assert part[mode]==ranks
                    else:part[mode]=ranks
                    results.append([k,repo,mode,measured])
                blocks.append(results)
                print('block',block+1,len(order),flush=True)
        io(HERE/'layout-measurements.json.gz',blocks)
        io(HERE/'layout-ranks.json.gz',allranks)
    io(HERE/'environment.json',dict(sqlite=sqlite3.sqlite_version,python=platform.python_version(),
                                    arch=platform.machine(),system=platform.system(),seed=SEED,
               inputs={k:sha256((p/'commits.json.gz').read_bytes()).hexdigest() for k,p in PANELS.items()}))

if __name__=='__main__':
    main()
