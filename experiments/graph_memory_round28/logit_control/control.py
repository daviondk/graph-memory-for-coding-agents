"""Disk-backed exact endpoint-logit controls with window-local reuse and certified early stopping."""
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from time import perf_counter_ns as now
import random
import sqlite3
import struct
import sys
import zlib
import numpy as np

D=Path(__file__).resolve().parent
PAR=D.parent/"retraction_db"
sys.path.insert(0,str(PAR))
from design import PRIVATE,read,save,sha
from study import SKY,TOP,prepared,pack

ARMS=("sky","raw-direct","zip-direct","raw-8-direct","zip-8-direct","raw-64-direct","zip-64-direct",
      "zip-8-local","zip-64-local","raw-8-bound","zip-8-bound","raw-64-bound","zip-64-bound")
PRIMARY="zip-64-bound"
BOUND_Q="SELECT score,ord,lo,hi,w FROM bounds.r WHERE q=? ORDER BY score DESC,ord"
LOGIT_Q="SELECT w,b FROM {}.r WHERE q=? ORDER BY w"
WINDOW_Q="SELECT b FROM {}.r WHERE q=? AND w=?"
DT=(("a","<f4"),("b","<f4"),("seg","<i2"),("lo","<i4"),("hi","<i4"))

def plan():
    p,cases,views,old=prepared()
    values={"parent":sha(PAR/"manifest.json"),"code":sha(Path(__file__)),"protocol":sha(D/"PROTOCOL_RU.md"),
            "capture":sha(D.parent/"revoked_evidence/forecast-seal.json"),"panel":p["panel"],"arms":ARMS}
    pf=D/"plan.json"
    if not pf.exists():save(pf,values)
    else:assert read(pf)=={**values,"arms":list(ARMS)}
    dest=PRIVATE/"logit_control"/sha(pf)
    dest.mkdir(parents=True,exist_ok=True)
    return p,cases,views,old,dest

def encode(ar,w):
    cols=[np.asarray(ar["base_"+str(w)+"_"+f],dtype=typ) for f,typ in DT]
    assert len(cols[0])<=384 and all(len(v)==len(cols[0]) for v in cols)
    return struct.pack("<H",len(cols[0]))+b"".join(v.tobytes() for v in cols)

def decode(raw):
    n=struct.unpack_from("<H",raw)[0];off=2;cols=[]
    for _,typ in DT:
        v=np.frombuffer(raw,count=n,offset=off,dtype=typ)
        off+=v.nbytes;cols.append(v)
    assert off==len(raw)
    return cols

@lru_cache(maxsize=385)
def geometry(n):
    i=np.arange(n)[:,None];j=i+np.arange(30)[None,:]
    return j<n, np.minimum(j,n-1)

def best(raw,w,l,h,exclude):
    a,b,seg,lo,hi=decode(raw)
    if not len(a):return None
    exists,ends=geometry(len(a))
    ok=exists & (seg[:,None]>=0) & (seg[:,None]==seg[ends])
    if exclude:ok &= (hi[ends]<=l)|(lo[:,None]>=h)
    score=np.where(ok,a[:,None]+b[ends],np.float32(-np.inf))
    loc=int(np.argmax(score));i,delta=divmod(loc,30);s=float(score[i,delta])
    if s==float("-inf"):return None
    return (s,(w*384+i)*30+delta,int(lo[i]),int(hi[i+delta]))

def better(x,y):
    return x is not None and (y is None or (-x[0],x[1])<(-y[0],y[1]))

def open_db(old,new,create):
    db=sqlite3.connect(":memory:")
    for n in ("raw","zip","bounds","top8","top64","sky"):
        path=(new if n in ("raw","zip","bounds") else old)/(n+".sqlite")
        db.execute("ATTACH DATABASE ? AS "+n,(str(path),))
        db.execute(f"PRAGMA {n}.cache_size=-32768")
    if create:
        for n in ("raw","zip"):
            db.execute(f"CREATE TABLE {n}.r(q INTEGER,w INTEGER,b BLOB,PRIMARY KEY(q,w)) WITHOUT ROWID")
        db.execute("CREATE TABLE bounds.r(q INTEGER,score REAL,ord INTEGER,lo INTEGER,hi INTEGER,w INTEGER, PRIMARY KEY(q,score DESC,ord)) WITHOUT ROWID")
    return db

def build():
    p,cases,views,old,new=plan()
    if (D/"build-seal.json").exists():return
    if (new/"raw.sqlite").exists():raise FileExistsError("Incomplete construction attempt")
    db=open_db(old,new,True);info=[]
    for ix,q in enumerate(p["qids"]):
        src=views/(q+".npz")
        assert sha(src)==cases[q]["arrays"]
        with np.load(src,allow_pickle=False) as ar:
            windows=cases[q]["states"]["base"]["windows"]
            for w in range(len(windows)):
                t=now();raw=encode(ar,w);ns_raw=now()-t
                t=now();compressed=zlib.compress(raw,6);ns_zip=now()-t
                t=now();r=best(raw,w,0,0,False);ns_bound=now()-t
                durations=[]
                for n,values in (("raw",(ix,w,raw)),("zip",(ix,w,compressed)),("bounds",(ix,*r,w) if r else None)):
                    t=now()
                    if values:db.execute("INSERT INTO "+n+".r VALUES ("+",".join("?" for v in values)+")",values)
                    durations.append(now()-t)
                info.append([q,w,len(raw),len(compressed),ns_raw,ns_zip,ns_bound,*durations])
        db.commit()
    db.close()
    save(D/"window-build.json.gz",info)
    save(D/"build-seal.json",{"plan":sha(D/"plan.json"),"rows":sha(D/"window-build.json.gz"),
           "files":{n:{"bytes":(new/(n+".sqlite")).stat().st_size,"sha":sha(new/(n+".sqlite"))} for n in ("raw","zip","bounds")}})

def lookup(db,m,ix,l,h):
    calls=0;blobs=0;windows=0;bounds_read=0;fallback=0
    if m=="sky":
        return db.execute(SKY,(ix,l,ix,h)).fetchone(),(1,0,0,0,0)
    terms=m.split("-");storage=terms[0];mode=terms[-1]
    if len(terms)==3:
        k=int(terms[1]);calls+=1;r=db.execute(TOP[k],(ix,l,h)).fetchone()
        if r is not None:return r,(calls,blobs,windows,bounds_read,fallback)
        fallback+=1
    def run(w,data):
        nonlocal blobs,windows
        blobs+=len(data);windows+=1
        return best(zlib.decompress(data) if storage=="zip" else data,w,l,h,True)
    found=None
    if mode=="direct":
        calls+=1
        for w,data in db.execute(LOGIT_Q.format(storage),(ix,)):
            candidate=run(w,data)
            if better(candidate,found):found=candidate
    else:
        calls+=1
        cur=db.execute(BOUND_Q,(ix,))
        for s,o,a,b,w in cur:
            bounds_read+=1;upper=(s,o,a,b)
            if mode=="bound" and not better(upper,found):break
            if b<=l or a>=h:candidate=upper
            else:
                calls+=1
                candidate=run(w,db.execute(WINDOW_Q.format(storage),(ix,w)).fetchone()[0])
            if better(candidate,found):found=candidate
    return found,(calls,blobs,windows,bounds_read,fallback)

def run():
    p,cases,_,old,new=plan()
    built=read(D/"build-seal.json");assert built["plan"]==sha(D/"plan.json")
    db=open_db(old,new,False);db.execute("PRAGMA query_only=1")
    oracle=read(PAR/"reference.json.gz");calls=0;work=[];counts={}
    # The incomplete top-K results never replace the independent oracle.
    for ix,q in enumerate(p["qids"]):
        counts[q]={}
        for case,r in oracle[q].items():
            l,h=r["ban"];a=r["answer"];d={}
            for m in ARMS:
                found,cost=lookup(db,m,ix,l,h)
                assert pack(found)==pack(a),(q,case,m,found,a)
                calls+=1;d[m]=cost
            if case in ("winner","record","random"):
                counts[q][case]=d
                if q in p["panel"]:work.append((q,ix,case,l,h))
        if (ix+1)%16==0:print("checked",ix+1,flush=True)
    for _,ix,_,l,h in work:
        for m in ARMS:lookup(db,m,ix,l,h)
    rng=random.Random(28297);times=[]
    for repeat in range(15):
        order=work.copy();rng.shuffle(order)
        for q,ix,case,l,h in order:
            ms=list(ARMS);rng.shuffle(ms)
            for m in ms:
                t=now();candidate,_=lookup(db,m,ix,l,h);out=pack(candidate);elapsed=now()-t
                times.append([repeat,q,case,m,elapsed])
        if (repeat+1)%5==0:print("timing",repeat+1,flush=True)
    db.close()
    save(D/"validation-costs.json.gz",counts);save(D/"latency.json.gz",times)
    save(D/"measurement-seal.json",{"plan":sha(D/"plan.json"),"build":sha(D/"build-seal.json"),"costs":sha(D/"validation-costs.json.gz"),
                                   "latency":sha(D/"latency.json.gz"),"strict":calls,"timings":len(times),"sqlite":sqlite3.sqlite_version})
if __name__=="__main__":
    if sys.argv[1]=="build":build()
    elif sys.argv[1]=="run":run()
    else:raise ValueError(sys.argv[1])
