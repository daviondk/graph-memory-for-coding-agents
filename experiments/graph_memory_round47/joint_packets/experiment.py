import gzip
import hashlib
from collections import defaultdict
from itertools import combinations,product
import json
from pathlib import Path
import random
import sqlite3
from time import perf_counter_ns as clock
from bank import DB,HERE,ROOT,SCALE,LIMIT,Snapshot,brute,build,choose,encode,library

SQL = ("select p.members from plane f join packet p on p.id=f.packet "
       "where f.pair_id=? order by f.v+f.a*?+f.b*? desc,f.priority limit 1")
AXIS_INFINITY=1<<55
def readonly(path):
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
def h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def save(path,data):
    raw=(json.dumps(data,sort_keys=True,separators=(',',':'))+'\n').encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix=='.gz' else raw)
def triangle(bounds,x,y):
    (lo1,hi1),(lo2,hi2)=bounds
    a=hi1 if x>=0 else -lo1
    b=hi2 if y>=0 else -lo2
    u,v=abs(x),abs(y)
    if u>a or v>b:return False
    if u==0 or v==0 or a==AXIS_INFINITY or b==AXIS_INFINITY:return True
    return u*b+v*a<=a*b
def small(lib):
    rng=random.Random(47028);tested=0
    for _ in range(180):
        n=rng.randint(1,8);ids=rng.sample(range(180),n)
        rows=[(i,rng.randrange(5),rng.randrange(-4,5)) for i in ids]
        budget=rng.randrange(9);s=Snapshot(rows,budget,rng.randint(0,budget))
        mark=[rng.randrange(4) for i in s.ids]
        planes,_=build(lib,s,mark);direct=s.native(lib,mark)
        for x,y in product(range(-3,4),repeat=2):
            assert brute(s,mark,x,y)==choose(planes,x,y)==direct(x,y)
            tested+=1
    return tested
def main():
    rng=random.Random(47029)
    lib=library();small_n=small(lib)
    db=readonly(DB)
    axis=readonly(ROOT/'graph_memory_round46/source_sensitivity/intervals.sqlite')
    tmp=HERE/'planes.build.sqlite';dest=HERE/'planes.sqlite'
    if tmp.exists():raise FileExistsError(tmp)
    out=sqlite3.connect(tmp)
    schema=clock()
    out.executescript("""
    create table packet(id integer primary key, members blob not null unique);
    create table pair(id integer primary key, q text, s text, t text, unique(q,s,t));
    create table plane(pair_id integer, priority integer, a integer, b integer, v integer, packet integer references packet(id),
                       primary key(pair_id,priority)) without rowid;
    """)
    build_ns=clock()-schema
    ids={};jobs={};slices={name:defaultdict(list) for name in ('uniform','stress')}
    ledger=[]
    idx=0
    for q,tr in db.execute('select q,trajectory_hash from query order by q'):
        ss=Snapshot([(i,c,round(v*SCALE)) for i,c,v in db.execute('select id,tokens,utility from node where q=? order by rank',(q,))])
        by=defaultdict(set)
        for ident,source in db.execute('select distinct id,source from span where q=? order by source,id',(q,)):by[source].add(ident)
        feasible={i for i,c in zip(ss.ids,ss.cost) if c<=ss.cap}
        names=sorted(by)
        combos=list(combinations(names,2))
        uniform=set(rng.sample(combos,min(len(combos),32)))
        heavy=sorted(names,key=lambda n:(-len(by[n]&feasible),n))[:6]
        stress=set(combinations(sorted(heavy),2))
        for s,t in sorted(uniform|stress):
            idx+=1
            sel=tuple(name for name,sam in [('uniform',uniform),('stress',stress)] if (s,t) in sam)
            for name in sel:slices[name][q].append(idx)
            mark=[int(i in by[s])+2*int(i in by[t]) for i in ss.ids]
            direct=ss.native(lib,mark)
            old=direct(0,0)
            lim=tuple(axis.execute('select lo,hi from valid where q=? and source=?',(q,v)).fetchone() for v in (s,t))
            start=clock()
            planes,states=build(lib,ss,mark)
            out.execute('insert into pair values(?,?,?,?)',(idx,q,s,t))
            for priority,(a,b,v,packet) in enumerate(planes):
                if packet not in ids:ids[packet]=out.execute('insert into packet(members) values(?)',(packet,)).lastrowid
                out.execute('insert into plane values(?,?,?,?,?,?)',(idx,priority,a,b,v,ids[packet]))
            elapsed=clock()-start
            build_ns+=elapsed
            jobs[idx]=(direct,planes,old,lim)
            grid=list(product((-LIMIT,-SCALE//16,0,SCALE//16,LIMIT),repeat=2))
            randoms=[(rng.randint(-LIMIT,LIMIT),rng.randint(-LIMIT,LIMIT)) for _ in range(32)]
            vals=[]
            for x,y in grid+randoms:
                full=direct(x,y)
                ans=out.execute(SQL,(idx,x,y)).fetchone()[0]
                assert full==ans==choose(planes,x,y)
                safe=triangle(lim,x,y)
                assert not safe or ans==old
                vals.append([x,y,ids[ans],int(safe)])
            ledger.append(dict(pair=idx,q=q,tr=tr,s=s,t=t,parts=sel,planes=len(planes),states=states,zero=ids[old],build_ns=elapsed,
                               m=sum(bool(m) for m,c in zip(mark,ss.cost) if c<=ss.cap),overlap=sum(m==3 and c<=ss.cap for m,c in zip(mark,ss.cost)),tests=vals))
    start=clock();out.commit();out.close();tmp.replace(dest);build_ns+=clock()-start
    view=readonly(dest)
    timings=[];reads={}
    for part,partition in slices.items():
        for regime in ('fresh','repeat'):
            memo={};hits=0;fixed={};trace_order=sorted(partition)
            for rep in range(5):
                rng.shuffle(trace_order)
                for i,q in enumerate(trace_order):
                    if rep==0 or regime=='fresh':
                        fixed[q]=[(j,rng.randint(-LIMIT,LIMIT),rng.randint(-LIMIT,LIMIT)) for j in partition[q] for _ in range(8)]
                    batch=fixed[q][:];rng.shuffle(batch)
                    def raw(j,x,y):return jobs[j][0](x,y)
                    def sql(j,x,y):return view.execute(SQL,(j,x,y)).fetchone()[0]
                    def ram(j,x,y):return choose(jobs[j][1],x,y)
                    def hybrid(j,x,y):
                        direct,_,old,lim=jobs[j]
                        return old if triangle(lim,x,y) else direct(x,y)
                    def cache(j,x,y):
                        nonlocal hits
                        key=(j,x,y)
                        if key in memo:
                            hits+=1;return memo[key]
                        packed=raw(j,x,y);memo[key]=packed;return packed
                    functions={'direct':raw,'sqlite':sql,'ram':ram,'hull':hybrid,'memo':cache}
                    modes=list(functions);split=(i+rep)%len(modes);modes=modes[split:]+modes[:split]
                    if rep%2:modes.reverse()
                    results={}
                    for name in modes:
                        fn=functions[name]
                        start=clock()
                        pack=[fn(j,x,y) for j,x,y in batch]
                        ns=clock()-start
                        results[name]=pack
                        if rep:timings.append([part,regime,rep,q,name,len(batch),ns])
                    assert all(p==results['direct'] for p in results.values())
            reads[part+'_'+regime]={'cached_weights':len(memo),'cache_hits_with_warmup':hits}
    output={'sources':h(DB),'protocol':h(HERE/'PROTOCOL_RU.md'),'control':h(HERE/'CONTROL_RU.md'),'axis':h(ROOT/'graph_memory_round46/source_sensitivity/intervals.sqlite'),
            'small':small_n,'pairs':len(ledger),'packets':len(ids),'build_ns':build_ns,'bytes':dest.stat().st_size,'plan':[r[-1] for r in view.execute('explain query plan '+SQL,(1,0,0))],'read_cache':reads}
    save(HERE/'pairs.json.gz',ledger);save(HERE/'times.json.gz',timings);save(HERE/'run.json',output)
    print('validated',len(ledger),'pairs;',small_n,'synthetic cases;',len(timings),'timing blocks')
if __name__=='__main__':main()
