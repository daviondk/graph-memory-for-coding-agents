"""Matched compiled controls, including global coordinate merging and isolated Windows working-set measurements."""
from collections import defaultdict
from pathlib import Path
from time import perf_counter_ns as now
import ctypes as ct
import hashlib
import random
import sqlite3
import subprocess
import sys
import numpy as np
import psutil
from bench import D,MATRIX,decode,binary,initialise,read,save,sha
from frontiers import pack_keys,record

LIB=Path("D:/CodexResearch/x20-r29-native-frontier/endpoint-v2.dll")
MODES=("scan","sparse","deque")
DLL=ct.CDLL(str(LIB))
PTR=np.ctypeslib.ndpointer
FN=DLL.endpoints
FN.argtypes=(ct.c_int,PTR(np.float32,flags="C_CONTIGUOUS"),PTR(np.float32,flags="C_CONTIGUOUS"),PTR(np.int16,flags="C_CONTIGUOUS"),
             ct.c_int,ct.c_int,PTR(np.int32,flags="C_CONTIGUOUS"),PTR(np.int32,flags="C_CONTIGUOUS"))
FN.restype=ct.c_int

def build(ws,name,k):
    active=[v for v in ws if np.any(v[2]>=0)]
    if not active:return ([],[]),0
    xs=np.unique(np.concatenate([v[4][v[2]>=0] for v in active]));ys=np.unique(np.concatenate([v[3][v[2]>=0] for v in active]))
    pre=np.zeros(len(xs),dtype=np.uint64);suf=np.zeros(len(ys),dtype=np.uint64);kernel=0
    for w,(a,b,seg,lo,hi) in enumerate(ws):
        ind=np.flatnonzero(seg>=0)
        if not len(ind):continue
        n=len(a);left=np.empty(n,np.int32);right=np.empty(n,np.int32)
        t=now();ret=FN(MODES.index(name),a,b,seg,n,k,left,right);kernel+=now()-t
        assert ret>=0
        start=left[ind];end=right[ind]
        assert np.all(start>=0) and np.all(end>=0)
        np.maximum.at(pre,np.searchsorted(xs,hi[ind]),pack_keys(a[start]+b[ind],(w*384+start)*k+ind-start))
        np.maximum.at(suf,np.searchsorted(ys,lo[ind]),pack_keys(a[ind]+b[end],(w*384+ind)*k+end-ind))
    output=[]
    for coords,values in ((xs,pre),(ys[::-1],suf[::-1])):
        values=np.maximum.accumulate(values);idx=np.flatnonzero(np.r_[True,values[1:]!=values[:-1]]&(values!=0))
        ords=np.uint64(0xffffffff)-(values[idx]&np.uint64(0xffffffff))
        output.append([(int(coords[i]),*record(ws,o,k)) for i,o in zip(idx,ords)])
    return tuple(output),kernel

def precision():
    rng=np.random.default_rng(29503);tested=0
    for step in range(28):
        n=(1,2,9,31,240,384,67)[step%7];seg=np.zeros(n,np.int16)
        if step%4:seg[::7]=-1
        if step%3==2:seg[9:]=3
        a=rng.choice(np.array([-1e8,-1,-0.,0.,np.nextafter(np.float32(1),np.float32(0)),1,1e8],dtype="f"),n)
        b=rng.choice(a,n);lo=np.arange(n,dtype=np.int32);ws=[(a,b,seg,lo,lo+1)]
        for k in (1,8,30,120,384):
            from frontiers import full_sort
            expected=binary(full_sort(ws,k))
            for m in MODES:
                assert binary(build(ws,m,k)[0])==expected,(step,m,k)
                tested+=1
    return tested

def plan():
    p,old,new=initialise();schedule=[]
    for rep in range(3):
        order=list(MODES);random.Random(29613+rep).shuffle(order)
        schedule.extend([[rep,m] for m in order])
    rows={"primary":sha(D/"plan.json"),"additional_protocol":sha(D/"NATIVE_RU.md"),"code":sha(D/"native.py"),"source":sha(D/"build_endpoint.cpp"),
          "library":sha(LIB),"compiler":"GCC 16.1.0 (MinGW-W64 x86_64-ucrt-posix-seh, Brecht Sanders r2)",
          "flags":"-O3 -std=c++17 -fno-fast-math -ffp-contract=off -static-libgcc -static-libstdc++ -shared -Wl,--no-insert-timestamp","schedule":schedule}
    path=D/"native-plan.json"
    if path.exists():assert read(path)==rows
    else:save(path,rows)
    return p,old,new,rows

def worker(rep,method):
    p,old,new,native=plan()
    db=sqlite3.connect(new/"raw.sqlite");ref=sqlite3.connect(old/"sky.sqlite")
    proc=psutil.Process();init=proc.memory_info();rows={}
    for ix,q in enumerate(p["ids"]):
        ws=[decode(v[0]) for v in db.execute("SELECT b FROM r WHERE q=? ORDER BY w",(ix,))]
        t=now();v,kern=build(ws,method,30);elapsed=now()-t;blob=binary(v)
        wanted=[ref.execute(f"SELECT bound,score,ord,lo,hi FROM {tbl} WHERE q=? ORDER BY bound {order}",(ix,)).fetchall()
                for tbl,order in (("pre","ASC"),("suf","DESC"))]
        assert binary(wanted)==blob,(q,method)
        rows[q]=[elapsed,kern,hashlib.sha256(blob).hexdigest()]
    save(D/"runs"/f"native-{method}-{rep}.json.gz",{"plan":sha(D/"native-plan.json"),"rows":rows,
         "peak_wset":proc.memory_info().peak_wset,"increment":proc.memory_info().peak_wset-init.rss})
    db.close();ref.close()

def main():
    p,old,new,r=plan()
    checks=precision()
    for rep,method in r["schedule"]:
        target=D/"runs"/f"native-{method}-{rep}.json.gz"
        if not target.exists():subprocess.run([sys.executable,"-B",str(Path(__file__)),"worker",str(rep),method],check=True,timeout=120)
    ids=p["ids"];a=defaultdict(list);dig={};mem=defaultdict(list)
    for rep,m in r["schedule"]:
        record=read(D/"runs"/f"native-{m}-{rep}.json.gz")
        assert record["plan"]==sha(D/"native-plan.json")
        mem[m].append([record["peak_wset"]/1048576,record["increment"]/1048576])
        for q,(ns,ker,h) in record["rows"].items():
            if q in dig:assert dig[q]==h
            dig[q]=h;a[m,q].append([ns/1e6,ker/1e6])
    result={}
    for m in MODES:
        x=np.array([np.median(a[m,q],axis=0) for q in ids]);v=np.percentile(x,[50,95],axis=0)
        result[m]={"p50_all_ms":v[0,0],"p95_all_ms":v[1,0],"p50_kernel_ms":v[0,1],"p95_kernel_ms":v[1,1],"working_set_MiB":mem[m]}
    from bench import PAR
    articles=read(PAR/"build-rows.json.gz");titles=sorted({v["article"] for v in articles.values()})
    groups=[[i for i,q in enumerate(ids) if articles[q]["article"]==t] for t in titles]
    seed=np.random.default_rng(29615);mat=np.array([[np.median(a[m,q],axis=0) for m in MODES] for q in ids])
    contrasts={}
    for j in (1,2):
        draws=seed.integers(len(titles),size=(10000,len(titles)))
        def effect(x):return (np.median(x[:,j,:],axis=0)/np.median(x[:,0,:],axis=0)).tolist()
        dist=[effect(mat[np.concatenate([groups[i] for i in sel])]) for sel in draws]
        contrasts[MODES[j]+"_over_scan"]={"end_to_end_and_kernel":effect(mat),"ci":np.percentile(dist,[2.5,97.5],axis=0).T.tolist()}
    save(D/"native-results.json",{"plan":sha(D/"native-plan.json"),"precision_checks":checks,"parity":len(r["schedule"])*len(ids),"methods":result,"contrasts":contrasts,
         "runs":{p.name:sha(p) for p in (D/"runs").glob("native-*.json.gz")}})
    print(result);print(contrasts)
if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="worker":worker(int(sys.argv[2]),sys.argv[3])
    else:main()
