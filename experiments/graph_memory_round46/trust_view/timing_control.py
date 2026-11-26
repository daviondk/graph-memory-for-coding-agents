import bisect
import ctypes as ct
from collections import defaultdict
import gzip
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter_ns as clock
from view import ROOT,SENS,DEMO,LOW,HIGH,INDEX_QUERY,Case,open_ro,arr

U16=ct.c_uint16
def main():
    directory=Path(tempfile.mkdtemp(prefix='trust-control-',dir=os.environ.get('SENS_BUILD_DIR') or None))
    target=directory/('direct.dll' if os.name=='nt' else 'direct.so')
    cmd=[os.environ.get('CXX') or shutil.which('g++'),'-O3','-std=c++17','-shared']
    cmd+=['-static'] if os.name=='nt' else ['-fPIC']
    subprocess.run(cmd+[str(ROOT/'direct.cpp'),'-o',str(target)],check=True)
    lib=ct.CDLL(str(target))
    native=lib.select_ids
    native.argtypes=[ct.c_int,ct.c_int,ct.POINTER(ct.c_int),ct.POINTER(ct.c_int64),ct.POINTER(ct.c_uint8),ct.c_int64,ct.POINTER(U16),ct.c_int,ct.POINTER(U16),ct.POINTER(U16)]
    native.restype=ct.c_int
    index=open_ro(ROOT/'view.sqlite')
    rows=open_ro(DEMO/'reader.sqlite')
    prepared={}
    scratch=(U16*600)()
    source_sets={}
    lookup={}
    start=clock()
    for q,s,begin,blob in index.execute('select q,source,start,members from edge join packet on id=packet_id order by q,source,start'):
        a,b=lookup.setdefault((q,s),([],[]))
        a.append(begin);b.append(blob)
    ram_init=clock()-start
    for q, in rows.execute('select q from query order by q'):
        raw=rows.execute('select id,tokens,utility from node where q=? order by rank',(q,)).fetchall()
        marks=defaultdict(set)
        for identity,s in rows.execute('select distinct id,source from span where q=? order by source,id',(q,)):
            marks[s].add(identity)
        source_sets[q]=sorted(marks)
        for s,ids in marks.items():
            c=Case(None,raw,ids)
            assert len(c.prefix)+len(c.units)<=600
            prepared[q,s]=(c.args,(arr(U16,c.prefix),len(c.prefix),arr(U16,c.units),scratch))
    def solve(q,s,d):
        args,end=prepared[q,s]
        n=native(*args,d,*end)
        return ct.string_at(scratch,2*n)
    def ram(q,s,d):
        begins,packs=lookup[q,s]
        return packs[bisect.bisect_right(begins,d)-1]
    def sql(q,s,d):
        return index.execute(INDEX_QUERY,(q,s,d)).fetchone()[0]
    rng=random.Random(46461)
    timings=[]
    caches={}
    for scenario in ('new','repeated'):
        warmed={}
        def memo(q,s,d):
            key=(q,s,d)
            result=warmed.get(key)
            if result is None:
                result=solve(q,s,d)
                warmed[key]=result
            return result
        functions={'direct':solve,'sql':sql,'ram':ram,'memo':memo}
        fixed={}
        orders=sorted(source_sets)
        for rep in range(5):
            rng.shuffle(orders)
            old_entries=len(warmed)
            for qi,q in enumerate(orders):
                if rep==0 or scenario=='new':
                    fixed[q]=[(s,rng.randint(LOW,HIGH)) for s in source_sets[q] for _ in range(8)]
                jobs=fixed[q][:]
                rng.shuffle(jobs)
                correct=[ram(q,s,d) for s,d in jobs]
                modes=list(functions)
                off=(qi+rep)%4
                modes=modes[off:]+modes[:off]
                if rep%2:modes.reverse()
                for name in modes:
                    f=functions[name]
                    start=clock()
                    result=[f(q,s,d) for s,d in jobs]
                    elapsed=clock()-start
                    assert result==correct
                    if rep:
                        timings.append([scenario,rep,q,name,len(jobs),elapsed])
            caches[scenario,rep]=[len(warmed),sum(len(v) for v in fixed.values())-(len(warmed)-old_entries)]
    raw=(json.dumps(timings,separators=(',',':'))+'\n').encode()
    (ROOT/'control-times.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    (ROOT/'control.json').write_text(json.dumps({'ram_load_ns':ram_init,'cache':{f'{k}-{i}':v for (k,i),v in caches.items()}},indent=2)+'\n','utf8')
    print(len(timings),caches)
if __name__=='__main__':main()
