"""Exact finite-domain index for an agent memory packet under one source-wide score change."""
from array import array
from collections import defaultdict
import ctypes as ct
import functools
import gzip
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import sys
from time import perf_counter_ns as clock

ROOT=Path(__file__).resolve().parent
SENS=ROOT.parent/'source_sensitivity'
sys.path.insert(0,str(SENS))
from experiment import BYTE, I, arr, bounds, compile_kernel, digest, pick, DEMO, SCALE

LOW,HIGH=-(SCALE//4),SCALE//4
INDEX_QUERY='select p.members from edge e join packet p on p.id=e.packet_id where e.q=? and e.source=? and e.start<=? order by e.start desc limit 1'

def encoded(ids):
    data=array('H',ids)
    if sys.byteorder!='little':
        data.byteswap()
    return data.tobytes()

class Case:
    def __init__(self,lib,rows,members):
        cut=0
        spent=0
        while cut<len(rows) and spent+rows[cut][1]<=1024:
            spent+=rows[cut][1]
            cut+=1
        tail=rows[cut:]
        self.prefix=[row[0] for row in rows[:cut]]
        self.units=[row[0] for row in tail]
        self.utils=[round(row[2]*SCALE) for row in tail]
        self.marks=[int(v in members) for v in self.units]
        self.lib=lib
        self.args=(len(tail),2048-spent,arr(ct.c_int,[row[1] for row in tail]),arr(I,self.utils),arr(BYTE,self.marks))
    def encode(self,mask):
        return encoded([*self.prefix,*(v for v,m in zip(self.units,mask) if m)])
    def direct(self,d):
        return self.encode(pick(self.lib,self.args,d))
    def solution(self,d):
        mask=pick(self.lib,self.args,d)
        return (self.encode(mask),sum(p for p,m in zip(self.utils,mask) if m),sum(v for v,m in zip(self.marks,mask) if m))

def make_envelope(solve):
    solve=functools.lru_cache(None)(solve)
    spans=[]
    def append(a,b,answer):
        if spans and spans[-1][2]==answer and spans[-1][1]==a-1:
            spans[-1]=(spans[-1][0],b,answer)
        else:
            spans.append((a,b,answer))
    def visit(a,b):
        left,v0,k0=solve(a)
        right,v1,k1=solve(b)
        if left==right:
            append(a,b,left)
            return
        assert a<b and k0<k1
        if a+1==b:
            append(a,a,left)
            append(b,b,right)
            return
        middle=min(b-1,max(a,(v0-v1)//(k1-k0)))
        visit(a,middle)
        visit(middle+1,b)
    visit(LOW,HIGH)
    assert spans[0][0]==LOW and spans[-1][1]==HIGH
    return spans,solve.cache_info().misses

def open_ro(path):
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)

def main():
    lib,compiler=compile_kernel()
    src=open_ro(DEMO/'reader.sqlite')
    valid=open_ro(SENS/'intervals.sqlite')
    tmp=ROOT/'view.build.sqlite'
    if tmp.exists():
        raise FileExistsError(tmp)
    out=sqlite3.connect(tmp)
    start=clock()
    out.executescript('create table packet(id integer primary key,members blob not null unique);create table edge(q text,source text,start integer,packet_id integer not null references packet(id),primary key(q,source,start)) without rowid;')
    build=clock()-start
    cases={}
    byq=defaultdict(list)
    stats={}
    packets={}
    old={}
    membership={}
    rng=random.Random(46209)
    checks=0
    for q,tr in src.execute('select q,trajectory_hash from query order by q'):
        rows=src.execute('select id,tokens,utility from node where q=? order by rank',(q,)).fetchall()
        grouped=defaultdict(set)
        for node,s in src.execute('select distinct id,source from span where q=? order by source,id',(q,)):
            grouped[s].add(node)
        stats[q]={'sources':len(grouped),'calls':0,'spans':0,'build_ns':0,'tr':tr,'boundary_probes':0}
        for s,marked in grouped.items():
            key=(q,s)
            c=Case(lib,rows,marked)
            cases[key]=c
            old.setdefault(q,c.direct(0))
            lo,hi=valid.execute('select lo,hi from valid where q=? and source=?',key).fetchone()
            start=clock()
            spans,num=make_envelope(c.solution)
            stats[q]['calls']+=num
            stats[q]['spans']+=len(spans)
            for a,b,packet in spans:
                # Unit numbers are local to a query; identical bytes can share storage only.
                if packet not in packets:
                    cursor=out.execute('insert into packet(members) values(?)',(packet,))
                    packets[packet]=cursor.lastrowid
                out.execute('insert into edge values(?,?,?,?)',(q,s,a,packets[packet]))
            elapsed=clock()-start
            build+=elapsed
            stats[q]['build_ns']+=elapsed
            probes=set()
            for a,b,packet in spans:
                probes.update((a,b))
                if a<=0<=b:
                    assert packet==old[q]
                    assert (a,b)==(max(LOW,lo),min(HIGH,hi))
            stats[q]['boundary_probes']+=len(probes)
            random_inputs=[rng.randint(LOW,HIGH) for _ in range(32)]
            for i,d in enumerate(random_inputs+sorted(probes)):
                oracle=c.direct(d)
                actual=out.execute(INDEX_QUERY,(q,s,d)).fetchone()[0]
                assert oracle==actual
                assert (oracle==old[q])==(lo<=d<=hi)
                checks+=1
                if i<8:
                    byq[q].append((s,d,oracle))
            membership[key]=(len(spans),num)
    start=clock()
    out.commit()
    out.close()
    tmp.replace(ROOT/'view.sqlite')
    build+=clock()-start
    index=open_ro(ROOT/'view.sqlite')

    def measure(q,mode,batch):
        start=clock()
        if mode=='direct':
            result=[cases[q,s].direct(d) for s,d,reference in batch]
        elif mode=='interval':
            result=[]
            for s,d,reference in batch:
                lo,hi=valid.execute('select lo,hi from valid where q=? and source=?',(q,s)).fetchone()
                result.append(old[q] if lo<=d<=hi else cases[q,s].direct(d))
        else:
            result=[index.execute(INDEX_QUERY,(q,s,d)).fetchone()[0] for s,d,reference in batch]
        duration=clock()-start
        assert all(res==row[2] for res,row in zip(result,batch))
        return duration
    runs=[]
    qlist=sorted(byq)
    modes=['direct','interval','index']
    for rep in range(5):
        rng.shuffle(qlist)
        for order,q in enumerate(qlist):
            batch=byq[q]
            rng.shuffle(batch)
            rotation=(order+rep)%3
            sequence=modes[rotation:]+modes[:rotation]
            if rep%2:sequence=sequence[::-1]
            for mode in sequence:
                elapsed=measure(q,mode,batch)
                if rep>0:
                    runs.append([rep,q,mode,len(batch),elapsed])
    result=dict(queries=stats,validated=checks,primary_scenarios=sum(v['sources'] for v in stats.values())*32,
        records=len(packets),changes=sum(n for n,ncall in membership.values()),items=len(cases),
        max_intervals=max(n for n,ncall in membership.values()),calls=sum(ncall for n,ncall in membership.values()),
        build_ns=build,bytes=(ROOT/'view.sqlite').stat().st_size,interval_bytes=(SENS/'intervals.sqlite').stat().st_size,
        compiler=compiler,query=INDEX_QUERY,plan=[r[-1] for r in index.execute('explain query plan '+INDEX_QUERY,('q01','s',1))],
        run_hash=digest(SENS/'run.json'),source_hash=digest(DEMO/'reader.sqlite'),protocol_hash=digest(ROOT/'PROTOCOL_RU.md'))
    (ROOT/'observations.json.gz').write_bytes(gzip.compress(json.dumps(runs,separators=(',',':')).encode(),mtime=0))
    (ROOT/'view-log.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n','utf8')
    print(result['items'],result['changes'],result['validated'],result['calls'],len(runs))
if __name__=='__main__':main()
