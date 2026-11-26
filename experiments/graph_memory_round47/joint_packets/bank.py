"""Factor source-independent candidates out of a two-parameter evidence packet."""
from array import array
import ctypes as ct
from functools import partial
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DB=ROOT/'graph_memory_round39/provenance_packet_demo/reader.sqlite'
U16=ct.c_uint16
BYTE=ct.c_uint8
I=ct.c_int64
SCALE=1<<32
LIMIT=SCALE//4
def typed(kind,data):
    return (kind*len(data))(*data)
def library():
    build_parent=os.environ.get('SENS_BUILD_DIR')
    tmp=Path(tempfile.mkdtemp(prefix='joint-packet-',dir=build_parent))
    binary=tmp/('kernels.dll' if os.name=='nt' else 'kernels.so')
    args=[os.environ.get('CXX') or shutil.which('g++'),'-O3','-std=c++17','-shared']
    args+=['-static'] if os.name=='nt' else ['-fPIC']
    subprocess.run(args+[str(HERE/'kernels.cpp'),'-o',str(binary)],check=True)
    lib=ct.CDLL(str(binary))
    pointer=ct.POINTER
    common=[ct.c_int,ct.c_int,pointer(ct.c_int),pointer(I),pointer(BYTE)]
    lib.packet2.argtypes=common+[I,I,pointer(U16),ct.c_int,pointer(U16),pointer(U16)]
    lib.packet2.restype=ct.c_int
    lib.complements.argtypes=common+[ct.c_int,pointer(ct.c_int),pointer(I),pointer(BYTE)]
    lib.complements.restype=None
    return lib
def encode(ids):
    a=array('H',ids)
    if sys.byteorder!='little':a.byteswap()
    return a.tobytes()

class Snapshot:
    def __init__(self,rows,budget=2048,threshold=1024):
        cut=0;spent=0
        while cut<len(rows) and spent+rows[cut][1]<=threshold:
            spent+=rows[cut][1];cut+=1
        self.head=[r[0] for r in rows[:cut]]
        self.ids=[r[0] for r in rows[cut:]]
        self.cost=[r[1] for r in rows[cut:]]
        self.profit=[r[2] for r in rows[cut:]]
        self.cap=budget-spent
        self.n=len(self.ids)
        self.c_args=(self.n,self.cap,typed(ct.c_int,self.cost),typed(I,self.profit))
        self.head_ids=typed(U16,self.head)
        self.tail_ids=typed(U16,self.ids)
    def packet(self,mask):
        return encode([*self.head,*(v for i,v in enumerate(self.ids) if mask & (1<<i))])
    def native(self,lib,marks):
        params=(*self.c_args,typed(BYTE,marks))
        suffix=(self.head_ids,len(self.head),self.tail_ids,(U16*(self.n+len(self.head)))())
        def run(x,y):
            length=lib.packet2(*params,x,y,*suffix)
            return ct.string_at(suffix[-1],length*2)
        return run

def better(value,mask,previous):
    return previous is None or value>previous[0] or (value==previous[0] and mask<previous[1])

def build(lib,snap,marks):
    # Within one class of cardinalities and cost, all completions are identical choices.
    # A smaller rank bit mask breaks ties consistently after adding disjoint complement bits.
    states={(0,0,0):(0,0)}
    for i,code in enumerate(marks):
        if not code or snap.cost[i]>snap.cap:continue
        step1=int(bool(code&1));step2=int(bool(code&2))
        c=snap.cost[i];u=snap.profit[i];bit=1<<i
        added={}
        for (a,b,c0),(v,m) in states.items():
            if c0+c>snap.cap:continue
            key=(a+step1,b+step2,c0+c)
            v1=v+u;m1=m|bit
            # Key translation by a fixed item is injective.
            if better(v1,m1,states.get(key)):
                added[key]=(v1,m1)
        states.update(added)
    costs=sorted({key[2] for key in states})
    pos={c:i for i,c in enumerate(costs)}
    capacity=typed(ct.c_int,[snap.cap-c for c in costs])
    width=(snap.n+7)//8
    totals=(I*len(costs))()
    data=(BYTE*(width*len(costs)))()
    lib.complements(*snap.c_args,typed(BYTE,marks),len(costs),capacity,totals,data)
    raw=bytes(data)
    comp=[int.from_bytes(raw[i*width:(i+1)*width],'little') for i in range(len(costs))]
    planes={}
    for (a,b,c),(v,m) in states.items():
        i=pos[c];joined=v+totals[i];mask=m|comp[i]
        if better(joined,mask,planes.get((a,b))):planes[a,b]=joined,mask
    # Sorting by complete-packet tie preference makes first-wins comparison exact.
    bank=[(a,b,v,snap.packet(mask)) for (a,b),(v,mask) in sorted(planes.items(),key=lambda row:row[1][1])]
    assert all(abs(v)+(a+b)*LIMIT<2**62 for a,b,v,p in bank)
    return bank,len(states)

def choose(bank,x,y):
    hi=None;answer=None
    for a,b,v,packet in bank:
        score=v+a*x+b*y
        if hi is None or score>hi:
            hi=score;answer=packet
    return answer

def brute(snap,marks,x,y):
    best=None
    for mask in range(1<<snap.n):
        use=[i for i in range(snap.n) if mask>>i&1]
        if sum(snap.cost[i] for i in use)>snap.cap:continue
        value=sum(snap.profit[i]+(x if marks[i]&1 else 0)+(y if marks[i]&2 else 0) for i in use)
        if better(value,mask,best):best=value,mask
    return snap.packet(best[1])

