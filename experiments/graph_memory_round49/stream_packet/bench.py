"""Interleaved native trials on whole streams and a frozen per-query quality forecast."""
from array import array
import ctypes as ct
from collections import defaultdict
from hashlib import sha256
import math,os,random,shutil,struct,subprocess,sys,tempfile
from time import perf_counter_ns
from fixture import D,load,save,digest

I=ct.c_int;L=ct.c_int64
def ar(kind,items):
    return (kind*len(items))(*items)
def library():
    root=os.environ.get("PACKET_BUILD_DIR")
    tmp=tempfile.mkdtemp(dir=root,prefix="stream49-")
    binary=os.path.join(tmp,"stream.dll" if os.name=="nt" else "stream.so")
    opts=["-static"] if os.name=="nt" else ["-fPIC"]
    subprocess.run([shutil.which("g++") or "g++","-O3","-std=c++17","-shared",*opts,str(D/"stream.cpp"),"-o",binary],check=True)
    fn=ct.CDLL(binary).serve;p=ct.POINTER
    fn.argtypes=[I]*7+[p(I)]*3+[p(L)]+[p(I)]*7+[p(L)]
    fn.restype=I
    return fn
class Input:
    def __init__(self,items,events,B=2048,T=1024):
        self.B=B;self.T=T;self.n=len(items);self.st=len(events);self.items=items;self.events=events
        off=[0];owners=[];eo=[0];src=[];counts=[]
        for b,i,c,v,a in items:owners.extend(a);off.append(len(owners))
        for changes in events:
            for a,k in changes:src.append(a);counts.append(k)
            eo.append(len(src))
        self.args=tuple(ar(k,[r[idx] for r in items]) for k,idx in [(I,0),(I,1),(I,2),(L,3)])+tuple(ar(I,arr) for arr in (off,owners,eo,src,counts))
        self.ends=(I*self.st)();self.ids=(I*(self.st*self.n+1))();self.stats=(L*3)()
    def trial(self,kernel,mode,period,cap=4):
        t=perf_counter_ns()
        size=kernel(self.n,self.st,self.B,self.T,mode,period,cap,*self.args,self.ends,self.ids,self.stats)
        elapsed=perf_counter_ns()-t
        assert size>=0
        flat=ct.string_at(self.ids,ct.sizeof(I)*size);ends=bytes(self.ends)
        return elapsed,tuple(self.stats),flat,ends
    def packs(self,flat,ends):
        all_ids=array("i");all_ids.frombytes(flat);lengths=array("i");lengths.frombytes(ends)
        prev=0;all_packets=[]
        for stop in lengths:
            all_packets.append(list(all_ids[prev:stop]));prev=stop
        assert prev==len(all_ids)
        return all_packets
def brute(s,step,cap):
    active=[r for r in s.items if r[0]<=step]
    support={}
    for updates in s.events[:step]:support.update(updates)
    room=s.B;head=[]
    for r in reversed(active):
        if room-r[2]<s.B-s.T:break
        head.append(r[1]);room-=r[2]
    tail=active[:len(active)-len(head)]
    optimum=None
    for mask in range(1<<len(tail)):
        used=[r for j,r in enumerate(tail) if mask>>j&1]
        if sum(r[2] for r in used)>room:continue
        utility=sum(r[3]+sum(min(cap,support.get(a,0))*(1<<28) for a in r[4]) for r in used)
        if optimum is None or (utility,-mask)>optimum[0]:
            optimum=((utility,-mask),[r[1] for r in reversed(used)])
    return head+optimum[1]
def small(fn):
    rng=random.Random(49008);checks=0
    for i in range(240):
        st=rng.randrange(2,7);n=rng.randrange(1,10);B=rng.randrange(1,12);T=rng.randrange(B+1)
        ids=rng.sample(range(100),n);birth=sorted(rng.choices(list(range(1,st+1)),k=n))
        rows=[[b,ids[j],rng.randrange(6),rng.randrange(-3,5),rng.sample([0,1,2],rng.randrange(3))] for j,b in enumerate(birth)]
        ev=[[[a,rng.randrange(5)] for a in rng.sample([0,1,2],rng.randrange(4))] for _ in range(st)]
        s=Input(rows,ev,B,T)
        for policy in (0,4):
            oracle=[brute(s,j,policy) for j in range(1,st+1)]
            for mode in (0,-1,1,4,16,64):
                for period in (0,1,4):
                    _,_,flat,ends=s.trial(fn,mode,period,policy)
                    observed=s.packs(flat,ends)
                    for j,(a,b) in enumerate(zip(oracle,observed),1):
                        assert b==(a if j==st or period and j%period==0 else []);checks+=1
    return checks
def main():
    sealed=load(D/"input-seal.json");assert sealed["file"]==digest((D/"input.json.gz").read_bytes())
    inputs=load(D/"input.json.gz");fn=library();nc=small(fn)
    cases={q:Input(items,events) for q,(traj,items,events) in inputs.items()}
    plans=[(mode,1) for mode in (0,-1,4,16,64)]+[(mode,p) for p in (0,4) for mode in (0,16)]
    goldfree={};correct={};times=[];rng=random.Random(49009)
    output=defaultdict(dict)
    for rep in range(6):
        order=list(cases);rng.shuffle(order)
        for q in order:
            s=cases[q];chosen=plans[:];rng.shuffle(chosen)
            for mode,p in chosen:
                elapsed,stats,flat,ends=s.trial(fn,mode,p)
                key=(q,p)
                if key not in correct:correct[key]=(flat,ends)
                else:assert correct[key]==(flat,ends),(q,mode,p,rep)
                if rep:times.append([q,rep,mode,p,elapsed,*stats])
            if rep==0:
                full=s.packs(*correct[q,1])
                for p in (0,4):
                    sparse=s.packs(*correct[q,p])
                    assert all(b==(a if i==s.st or p and i%p==0 else []) for i,(a,b) in enumerate(zip(full,sparse),1))
                _,_,ff,ee=s.trial(fn,0,1,0);zero=s.packs(ff,ee)
                for step in sorted({s.st,8}):
                    if step>s.st:continue
                    view=[r for r in s.items if r[0]<=step]
                    # Original reader's order is the compact item index in its published ranking.
                    dense=[];budget=s.B
                    for _,ident,c,_,_ in sorted(view,key=lambda r:r[1]):
                        if c<=budget:dense.append(ident);budget-=c
                    output[q][str(step)]=dict(full=full[step-1],no_support=zero[step-1],dense=dense)
                output[q]["last"]=s.st
        print("repetition",rep,flush=True)
    save(D/"packets.json.gz",output);save(D/"timing.json.gz",times)
    save(D/"forecast-seal.json",dict(inputs=sealed["file"],packets=digest((D/"packets.json.gz").read_bytes()),
        times=digest((D/"timing.json.gz").read_bytes()),code=digest((D/"stream.cpp").read_bytes()),small=nc,
        actual=len(cases),boundaries=sum(s.st for s in cases.values()),modes=plans,
        complete_order_hash=digest(b"".join(sha256(correct[k][0]+correct[k][1]).digest() for k in sorted(correct)))))
if __name__=="__main__": main()
