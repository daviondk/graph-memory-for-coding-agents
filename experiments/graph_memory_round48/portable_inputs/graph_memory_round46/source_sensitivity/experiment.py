"""Build integer source intervals and compare all reported answers with direct reoptimization."""
from collections import Counter, defaultdict
import ctypes as ct
from hashlib import sha256
from itertools import product
import json
import gzip
import os
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import tempfile
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parent
DEMO=ROOT.parents[1]/'graph_memory_round39/provenance_packet_demo'
INF=1<<55
SCALE=1<<32
GRID=tuple((sign*SCALE)//den for den in (64,16,4) for sign in (-1,1))
I=ct.c_int64
BYTE=ct.c_uint8
def digest(p):
    return sha256(p.read_bytes()).hexdigest()
def compile_kernel():
    compiler=os.environ.get('CXX') or shutil.which('g++')
    if not compiler:
        raise RuntimeError('Install a C++17 compiler or set CXX.')
    suffix='.dll' if os.name=='nt' else '.so'
    folder=Path(tempfile.mkdtemp(prefix='source-interval-',dir=os.environ.get('SENS_BUILD_DIR') or None))
    binary=folder/('kernel'+suffix)
    subprocess.run([compiler,'-std=c++17','-O3','-shared',*(['-static','-static-libgcc','-static-libstdc++'] if os.name=='nt' else ['-fPIC']),str(ROOT/'kernel.cpp'),'-o',str(binary)],check=True)
    library=ct.CDLL(str(binary))
    shared=[ct.c_int,ct.c_int,ct.POINTER(ct.c_int),ct.POINTER(I),ct.POINTER(BYTE)]
    library.full_select.argtypes=[*shared,I,ct.POINTER(BYTE)]
    library.interval.argtypes=[*shared,ct.POINTER(BYTE),ct.POINTER(I)]
    library.full_select.restype=library.interval.restype=None
    return library,subprocess.check_output([compiler,'--version'],text=True).splitlines()[0]
def arr(kind,values):
    return (kind*len(values))(*values)
def pick(lib,args,delta):
    out=(BYTE*args[0])()
    lib.full_select(*args,delta,out)
    return bytes(out)
def bounds(lib,args,old):
    out=(I*5)()
    lib.interval(*args,arr(BYTE,old),out)
    assert not out[4] and out[0]<=0<=out[1]
    return tuple(out[:4])
def brute(cost,utility,marked,cap,delta):
    best=(0,0)
    for mask in range(1,1<<len(cost)):
        idx=[i for i in range(len(cost)) if (mask>>i)&1]
        if sum(cost[i] for i in idx)<=cap:
            score=sum(utility[i]+delta*marked[i] for i in idx)
            best=max(best,(score,-mask))
    return bytes(int((-best[1]>>i)&1) for i in range(len(cost)))
def small_test(lib):
    rng=random.Random(46071)
    count=0
    for trial in range(200):
        n=rng.randint(0,8)
        cs=[rng.randrange(5) for i in range(n)]
        us=[rng.randrange(-4,5) for i in range(n)]
        mask=[rng.randrange(2) for i in range(n)]
        capacity=rng.randrange(10)
        args=(n,capacity,arr(ct.c_int,cs),arr(I,us),arr(BYTE,mask))
        old=brute(cs,us,mask,capacity,0)
        assert pick(lib,args,0)==old
        lo,hi,*_=bounds(lib,args,old)
        for d in range(-26,27):
            truth=brute(cs,us,mask,capacity,d)
            assert truth==pick(lib,args,d) and (truth==old)==(lo<=d<=hi)
            count+=1
    return count
def main():
    lib,compiler=compile_kernel()
    synthetic=small_test(lib)
    file=DEMO/'reader.sqlite'
    db=sqlite3.connect(file.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    refs=json.loads((DEMO/'reference.json').read_bytes())
    ledger=[]
    checks=Counter()
    projections={}
    save_to=ROOT/'intervals.sqlite'
    # Generate into a fresh sibling and atomically replace only the output artifact.
    tmp=ROOT/'intervals.build.sqlite'
    if tmp.exists():
        raise FileExistsError(tmp)
    intervals=sqlite3.connect(tmp)
    intervals.execute('create table valid(q text, source text, lo integer not null, hi integer not null, primary key(q,source)) without rowid')
    for q,tr in db.execute('select q,trajectory_hash from query order by q'):
        rows=db.execute('select id,tokens,utility from node where q=? order by rank',(q,)).fetchall()
        by_source=defaultdict(set)
        for identity,source in db.execute('select distinct id,source from span where q=? order by source,id',(q,)):
            by_source[source].add(identity)
        prefix=0
        spent=0
        while prefix<len(rows) and spent+rows[prefix][1]<=1024:
            spent+=rows[prefix][1]
            prefix+=1
        tail=rows[prefix:]
        cap=2048-spent
        n=len(tail)
        costs=arr(ct.c_int,[c for _,c,_ in tail])
        utility=arr(I,[round(v*SCALE) for _,_,v in tail])
        old=pick(lib,(n,cap,costs,utility,arr(BYTE,[0]*n)),0)
        packet=[r[0] for r in rows[:prefix]]+[r[0] for i,r in enumerate(tail) if old[i]]
        assert packet==refs[q]['ids']
        projections[q]={'trajectory':tr,'nodes':len(rows),'suffix':n,'sources':len(by_source)}
        for source,ids in by_source.items():
            marked=[int(identity in ids) for identity,_,_ in tail]
            eligible=[i for i in range(n) if marked[i] and costs[i]<=cap]
            k=sum(old[i] for i in eligible)
            args=(n,cap,costs,utility,arr(BYTE,marked))
            start=perf_counter_ns()
            lo,hi,tie_lo,tie_hi=bounds(lib,args,old)
            build=perf_counter_ns()-start
            intervals.execute('insert into valid values(?,?,?,?)',(q,source,lo,hi))
            limits={0,*(v+d for v in (lo,hi) if abs(v)!=INF for d in (-1,0,1))}
            samples=[]
            for d in sorted(set(GRID)|limits):
                start=perf_counter_ns()
                actual=pick(lib,args,d)
                direct=perf_counter_ns()-start
                same=old==actual
                sign=(d==0 or (d>0 and k==len(eligible)) or (d<0 and k==0))
                allowed=lo<=d<=hi
                checks['direct_checks']+=1
                checks['boundary_grid_checks']+=int(d in limits)
                assert same==allowed and (not sign or same)
                hamming=sum(a!=b for a,b in zip(old,actual))
                samples.append([d,int(same),int(sign),hamming,direct])
            ledger.append(dict(q=q,source=source,tr=tr,m=len(eligible),k=k,lo=lo,hi=hi,tie_lo=tie_lo,tie_hi=tie_hi,build_ns=build,samples=samples))
    assert len(ledger)==2528 and len(projections)==40
    intervals.commit()
    intervals.close()
    tmp.replace(save_to)
    encoded=(json.dumps(ledger,separators=(',',':'))+'\n').encode()
    (ROOT/'sources.json.gz').write_bytes(gzip.compress(encoded,mtime=0))
    receipt=dict(queries=projections,synthetic=synthetic,compiler=compiler,checks=dict(checks),source_sha256=digest(file),protocol_sha256=digest(ROOT/'PROTOCOL_RU.md'),kernel_sha256=digest(ROOT/'kernel.cpp'),ledger_sha256=digest(ROOT/'sources.json.gz'),grid=GRID,inf=INF)
    (ROOT/'run.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n','utf8')
    print(len(ledger),dict(checks),synthetic)
if __name__=='__main__':main()
