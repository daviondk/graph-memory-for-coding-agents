"""Use independent worker processes for peak working set and per-question exact build timing."""
from collections import defaultdict
from pathlib import Path
from time import perf_counter_ns as clock
import argparse
import hashlib
import platform
import random
import sqlite3
import struct
import subprocess
import sys
import numpy as np
import psutil
from frontiers import METHODS

D=Path(__file__).resolve().parent;W=D.parents[1]
sys.path.insert(0,str(W/"graph_memory_round28/logit_control"))
from control import D as LOGIT, PAR, decode, plan as logit_plan, read, save, sha
MATRIX=("full_sort","stream","endpoint_matrix","dyadic")
def binary(sides):
    return b"".join(struct.pack("<I",len(rows))+b"".join(struct.pack("<ifIii",bound,score,order,lo,hi) for bound,score,order,lo,hi in rows) for rows in sides)

def tests():
    rng=np.random.default_rng(28315);cases=[]
    for n in (1,2,9,31,67):
        seg=np.repeat(np.arange(1+n//7),7)[:n].astype(np.int16);seg[::5]=-1
        lo=np.arange(n,dtype=np.int32)*2;hi=lo+1
        a=rng.normal(size=n).astype("f");b=rng.normal(size=n).astype("f")
        cases.extend([[(a,b,seg,lo,hi)],[(np.zeros(n,"f"),np.zeros(n,"f"),seg,lo,hi)]])
    a=np.array([np.nextafter(np.float32(1),np.float32(0)),1,0],dtype="f");b=np.array([0,0,1e8],dtype="f")
    assert a[0]<a[1] and a[0]+b[2]==a[1]+b[2]
    cases+=[[(a,b,np.array([0,0,0]),np.arange(3),np.arange(3)+1)],[(b,a,np.array([0,0,0]),np.arange(3),np.arange(3)+1)],
            [(b,a,np.array([0,-1,0]),np.arange(3),np.arange(3)+1)],[]]
    result=0
    for ws in cases:
        for k in (1,2,8,30,120):
            expect=binary(METHODS["full_sort"](ws,k))
            for m in MATRIX:
                assert binary(METHODS[m](ws,k))==expect,(m,k,ws)
                result+=1
    return result

def initialise():
    p,_,_,old,new=logit_plan();q=p["qids"]
    stress=sorted(q,key=lambda s:hashlib.sha256(("r29-width|"+s).encode()).digest())[:8]
    methods=[]
    for rep in range(3):
        order=list(MATRIX);random.Random(29401+rep).shuffle(order)
        methods.extend([[rep,m,30] for m in order])
    for k in (8,120):methods.extend([[0,m,k] for m in MATRIX])
    source={"ids":q,"stress":stress,"runs":methods,"protocol":sha(D/"PROTOCOL_RU.md"),"algorithms":sha(D/"frontiers.py"),
            "runner":sha(D/"bench.py"),"parent":sha(LOGIT/"manifest.json"),"reference":sha(PAR/"manifest.json"),"test_comparisons":tests()}
    plan=D/"plan.json"
    if plan.exists():assert read(plan)==source
    else:save(plan,source)
    return source,old,new

def worker(rep,method,k):
    schedule,old,new=initialise();qids=schedule["ids"]
    if k!=30:qids=[q for q in qids if q in schedule["stress"]]
    db=sqlite3.connect(new/"raw.sqlite");ref=sqlite3.connect(old/"sky.sqlite")
    db.execute("PRAGMA query_only=1");ref.execute("PRAGMA query_only=1")
    proc=psutil.Process();initial=proc.memory_info();rows={}
    for q in qids:
        ix=schedule["ids"].index(q);start=clock()
        ws=[decode(row[0]) for row in db.execute("SELECT b FROM r WHERE q=? ORDER BY w",(ix,))]
        after=clock();v=METHODS[method](ws,k);ns=clock()-after;blob=binary(v)
        if k==30:
            orig=[ref.execute(f"SELECT bound,score,ord,lo,hi FROM {t} WHERE q=? ORDER BY bound {order}",(ix,)).fetchall() for t,order in (("pre","ASC"),("suf","DESC"))]
            assert binary(orig)==blob,(q,method,k)
        rows[q]={"ns":ns,"input_ns":after-start,"bytes":len(blob),"tokens":sum(len(w[0]) for w in ws),
                 "records":sum(map(len,v)),"digest":hashlib.sha256(blob).hexdigest()}
    peak=proc.memory_info()
    name=f"k{k}-{method}-r{rep}.json.gz"
    save(D/"runs"/name,{"rows":rows,"method":method,"repeat":rep,"K":k,"initial_rss":initial.rss,"initial_peak":initial.peak_wset,
          "peak_wset":peak.peak_wset,"increment_over_initial_wset":peak.peak_wset-initial.rss,
          "increment_over_prior_peak":peak.peak_wset-initial.peak_wset,"python":platform.python_version(),"numpy":np.__version__,
          "plan":sha(D/"plan.json")})
    db.close();ref.close()
def run():
    p,_,_=initialise();(D/"runs").mkdir(exist_ok=True)
    for rep,method,k in p["runs"]:
        path=D/"runs"/f"k{k}-{method}-r{rep}.json.gz"
        if path.exists():
            assert read(path)["plan"]==sha(D/"plan.json");continue
        print("start",k,method,rep,flush=True)
        subprocess.run([sys.executable,"-B",str(Path(__file__)),"worker",str(rep),method,str(k)],check=True,timeout=180)
    print("complete",len(p["runs"]),flush=True)
if __name__=="__main__":
    if sys.argv[1]=="run":run()
    elif sys.argv[1]=="worker":worker(int(sys.argv[2]),sys.argv[3],int(sys.argv[4]))
    elif sys.argv[1]=="tests":print(tests())
    else:raise ValueError(sys.argv[1])
