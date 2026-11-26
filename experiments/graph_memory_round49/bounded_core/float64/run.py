"""Compare the guarded selector to all archived native binary64 packets on identical inputs."""
import ctypes as ct
from array import array
from collections import defaultdict
import gzip,json,os,random,struct,subprocess,sys,tempfile
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import numpy as np
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent))
from bench_core import Case,read,write,h,S
def build():
    stage=Path(tempfile.mkdtemp(dir=os.environ.get("PACKET_BUILD_DIR")))
    file=stage/("guard.dll" if os.name=="nt" else "guard.so")
    subprocess.run(["g++","-O3","-std=c++17","-shared","-static" if os.name=="nt" else "-fPIC","-ffp-contract=off",str(D/"guard.cpp"),"-o",str(file)],check=True)
    fn=ct.CDLL(str(file)).solve
    i=ct.c_int;l=ct.c_int64;p=ct.POINTER
    fn.argtypes=[i]*5+[p(i)]*3+[p(l),p(ct.c_double)]+[p(i)]*2+[p(l)]
    fn.restype=i
    return fn
def specialize(case,v):
    f=(ct.c_double*len(v))(*v)
    return (*case.cols[:4],f,*case.cols[4:])
def solve(fn,case,cols,m):
    start=perf_counter_ns();n=fn(*case.args,m,*cols);elapsed=perf_counter_ns()-start
    assert n>=0
    return elapsed
def tiny(fn):
    rng=random.Random(49852);checked=0
    for j in range(420):
        n=rng.randint(1,9);c=[rng.randrange(6) for _ in range(n)]
        b=rng.randrange(13);t=rng.randrange(b+1);ids=list(range(n));rng.shuffle(ids)
        # Values differing by less than one Q32 and repeated exact values stress the guard.
        vals=[rng.randrange(9)/8+2**-40*rng.randrange(1,5) for _ in ids]
        q=[round(y*2**32) for y in vals]
        case=Case({"cost":c,"states":[[1,1,ids,q,[]]]},b,t)
        cols=specialize(case,vals)
        solve(fn,case,cols,0);oracle=case.copy()
        solve(fn,case,cols,1);assert oracle==case.copy()
        checked+=1
    return checked
def main():
    assert sys.byteorder=="little"
    fn=build();checks=tiny(fn);sources=read(D/"inputs.json")
    rng=random.Random(49853);counts={}
    for seed in (13,17,29,37,41):
        path=S/f"input-{seed}.json.gz";vf=D/f"weights-{seed}.f64.gz"
        receipt=sources[str(seed)];assert receipt["source"]==h(path) and receipt["binary"]==h(vf)
        vals=np.frombuffer(gzip.decompress(vf.read_bytes()),dtype="<f8");src=read(path)
        cases={};off=0;actual=0
        for q,case in sorted(src.items()):
            obj=Case(case);n=sum(len(s[2]) for s in obj.seq)
            v=vals[off:off+n];off+=n
            assert np.isfinite(v).all() and np.all(v>0)
            assert np.array_equal(np.rint(v*2**32).astype(np.int64),[i for st in obj.seq for i in st[3]])
            assert len(v)*2**-52<0.01
            cases[q]=obj,specialize(obj,v)
        assert off==len(vals)
        times=[];ops={}
        for rep in range(6):
            order=list(cases);rng.shuffle(order)
            for q in order:
                case,cols=cases[q];modes=[0,1];rng.shuffle(modes)
                for mode in modes:
                    elapsed=solve(fn,case,cols,mode)
                    assert case.copy()==[r[-1] for r in case.seq],(q,seed,mode)
                    if rep:times.append([q,rep,mode,elapsed])
                    elif mode:
                        actual+=len(case.seq)
                        ops[q]=list(case.stats)[:3*len(case.seq)]
        counts[seed]=actual
        write(D/f"runs-{seed}.json.gz",[times,ops])
        print("verified original floating packets",seed,actual,flush=True)
    write(D/"seal.json",dict(code=h(D/"guard.cpp"),protocol=h(D/"PROTOCOL_RU.md"),checked=counts,synthetic=checks,
        files={f.name:h(f) for f in sorted(D.glob("runs-*.json.gz"))}))
if __name__=="__main__":main()
