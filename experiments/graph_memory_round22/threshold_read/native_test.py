"""Build the C++17 operators, exercise real SQLite C statements and measure paired timings."""
from pathlib import Path
from collections import defaultdict
from ctypes import CDLL,c_int,c_char_p,c_void_p
from contextlib import contextmanager
from tempfile import TemporaryDirectory
import os
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time

from measure import HERE,load,put,sha,select,boot_ratio
from operators import np,index,suffix_bounds
from sqlite_test import PRIVATE,DB,fixture

ARMS=("vector","heap","stream","sql","final")
def build():
    compiler=Path(shutil.which("g++"))
    runtime=Path(sys.base_prefix)/"DLLs/sqlite3.dll"
    assert runtime.exists()
    source=HERE/"sqlite_operators.cpp";binary=PRIVATE/"compiled"/("operators-"+sha(source)[:16]+".dll")
    binary.parent.mkdir(parents=True,exist_ok=True)
    flags=["-O3","-std=c++17","-ffp-contract=off","-shared","-static-libstdc++","-static-libgcc"]
    if not binary.exists():subprocess.run([str(compiler),*flags,str(source),str(runtime),"-o",str(binary)],check=True)
    put(HERE/"native-build.json",{"source_sha":sha(source),"binary_sha":sha(binary),"binary":binary.name,"runtime_sha":sha(runtime),
        "runtime_name":runtime.name,"sqlite_version":sqlite3.sqlite_version,"compiler":subprocess.check_output([str(compiler),"--version"],text=True).splitlines()[0],"flags":flags,
        "protocol":sha(HERE/"NATIVE_PROTOCOL_RU.md")})
    return compiler,runtime,binary

def initialize():
    compiler,runtime,binary=build()
    search=[os.add_dll_directory(str(s)) for s in (runtime.parent,compiler.parent)]
    lib=CDLL(str(binary));lib.memory_open.argtypes=[c_char_p];lib.memory_open.restype=c_void_p
    lib.memory_close.argtypes=[c_void_p];lib.memory_close.restype=None
    lib.memory_query.argtypes=[c_void_p]+[c_int]*6+[c_void_p]*8;lib.memory_query.restype=c_int
    return lib,search

@contextmanager
def connection(lib,path):
    h=lib.memory_open(str(path).encode("utf8"));assert h
    try:yield h
    finally:lib.memory_close(h)


class Input:
    def __init__(self,signal,prior,cost):
        self.n=len(cost);ix=index(prior,cost)
        self.arrays=[np.ascontiguousarray(a) for a in (np.array(signal,dtype="float64"),suffix_bounds(signal),ix.prior,ix.costs,ix.by_prior.astype("int64"),ix.by_cost.astype("int64"))]
        self.out=np.empty(self.n,dtype="int32");self.meta=np.zeros(6,dtype="int64")
        self.ptrs=[a.ctypes.data for a in self.arrays+[self.out,self.meta]]
    def run(self,lib,db,mode,q,t,pol,budget,expected):
        start=time.perf_counter_ns()
        count=lib.memory_query(db,mode,q,t,self.n,pol=="skip",budget,*self.ptrs)
        wall=time.perf_counter_ns()-start
        assert count>=0 and self.out[:count].tolist()==expected,(q,t,mode,pol,count,expected)
        return self.meta.tolist(),wall


def edge_cases(lib):
    rng=np.random.default_rng(5421)
    with TemporaryDirectory(dir=PRIVATE) as tmp:
        db=Path(tmp)/"synthetic.sqlite";c=sqlite3.connect(db)
        c.executescript("create table prior(t,unit,value,cost,primary key(t,unit));create table dense(q,r,unit,g,primary key(q,r));create table final(q,k,unit,cost,primary key(q,k));")
        fixtures=[]
        for q in range(128):
            n=int(rng.integers(1,40));p=rng.integers(-4,5,n).astype(float).tolist();g=rng.integers(-3,4,n).astype(float).tolist()
            if q%11==0:p=[0.]*n;g=[1.]*n
            costs=rng.integers(1,20,n).tolist();o=rng.permutation(n).tolist();b=0 if q%17==0 else int(rng.integers(0,1+sum(costs)))
            full=sorted(range(n),key=lambda j:(-(g[j]+p[o[j]]),j))
            c.executemany("insert into prior values (?,?,?,?)",[(q,j,p[j],costs[j]) for j in range(n)])
            c.executemany("insert into dense values (?,?,?,?)",[(q,j,o[j],g[j]) for j in range(n)])
            c.executemany("insert into final values (?,?,?,?)",[(q,j,o[k],costs[o[k]]) for j,k in enumerate(full)])
            arms={}
            for pol in ("prefix","skip"):
                left=b;keep=[]
                for j in full:
                    cost=costs[o[j]]
                    if cost<=left:keep.append(o[j]);left-=cost
                    elif pol=="prefix":break
                arms[pol]=keep
            fixtures.append((Input(g,p,costs),b,arms))
        c.commit();c.close()
        with connection(lib,db) as h:
            for q,(inp,b,e) in enumerate(fixtures):
                for i in range(len(ARMS)):
                    for pol in e:inp.run(lib,h,i,q,q,pol,b,e[pol])
    return len(fixtures)*len(ARMS)*2


def run():
    lib,libraries=initialize()
    edge=edge_cases(lib);assert sha(DB)==load(HERE/"sqlite-build.json")["db_sha"]
    rows={};seen=0
    for t,tr in enumerate(fixture()):
        inp=Input(tr["signal"],tr["prior"],tr["costs"])
        for r in sorted(tr["queries"],key=lambda r:r["q"]):
            rows[r["q"]]=(t,seen,tr["t"],inp,r["expected"]);seen+=1
    chosen=select(rows);rng=random.Random(17731);checks=[];times=[]
    with connection(lib,DB) as db:
        for name in sorted(rows):
            t,q,tid,inp,exp=rows[name];facts={}
            for i,mode in enumerate(ARMS):
                for pol in ("prefix","skip"):
                    run,_=inp.run(lib,db,i,q,t,pol,2048,exp[pol])
                    facts[pol+"/"+mode]=dict(zip(("rows","scored","vm","cache_hits","cache_misses"),run[:5],strict=True))
            checks.append({"q":name,"t":tid,"n":inp.n,"counters":facts})
        for name in sorted(chosen):
            t,q,tid,inp,exp=rows[name]
            for rep in range(7):
                order=[(pol,j) for pol in ("prefix","skip") for j in range(len(ARMS))]
                rng.shuffle(order);inside={};outside={};counters={}
                for pol,j in order:
                    obs,wall=inp.run(lib,db,j,q,t,pol,2048,exp[pol]);arm=pol+"/"+ARMS[j]
                    inside[arm]=obs[5];outside[arm]=wall;counters[arm]=obs[2:5]
                times.append({"q":name,"t":tid,"rep":rep,"order":[p+"/"+ARMS[j] for p,j in order],"inside_ns":inside,"outside_ns":outside,"vm_hits_misses":counters})
    assert libraries
    put(HERE/"native-checks.json.gz",checks);put(HERE/"native-times.json.gz",times)
    sums={m:{k:sum(r["counters"][m][k] for r in checks) for k in z} for m,z in checks[0]["counters"].items()}
    by=defaultdict(list)
    for r in times:by[r["q"]].append(r)
    results={}
    for metric in ("inside_ns","outside_ns"):
        med={q:{"t":rs[0]["t"],**{m:statistics.median(r[metric][m] for r in rs) for m in sums}} for q,rs in by.items()}
        for m in sums:
            pol,method=m.split("/");v=np.asarray([rs[m] for rs in med.values()])/1000
            base=np.median([rs[pol+"/vector"] for rs in med.values()])/1000
            results[metric+"/"+m]={"median_us":float(np.median(v)),"p95_us":float(np.quantile(v,.95)),"ratio":float(np.median(v)/base),
                 "ratio_ci":boot_ratio(med,pol,method) if method!="vector" else [1.,1.]}
    put(HERE/"native-results.json",{"real_comparisons":len(checks)*len(sums),"synthetic_comparisons":edge,"timed_questions":len(chosen),"timed_trajectories":len({r["t"] for r in times}),
         "repeats":7,"totals":sums,"times":results,"warm_timing_cache_misses":{m:sum(r["vm_hits_misses"][m][2] for r in times) for m in sums},
         "files":{n:sha(HERE/n) for n in ("sqlite_operators.cpp","native_test.py","native-build.json","NATIVE_PROTOCOL_RU.md","sqlite-build.json","native-checks.json.gz","native-times.json.gz")}})
    print("Matched",len(checks)*len(sums),"real and",edge,"synthetic native SQLite selections.",flush=True)

if __name__=="__main__":run()

