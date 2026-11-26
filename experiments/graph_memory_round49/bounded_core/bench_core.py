"""Cross-check the full ordered output across causal snapshots, then time the four exact plans."""
import ctypes as ct
from hashlib import sha256
from itertools import accumulate
import gzip,json,os,random,subprocess,tempfile
from pathlib import Path
from time import perf_counter_ns

D=Path(__file__).resolve().parent
S=D.parent/"learned_stream"
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def write(p,data):
    b=(json.dumps(data,separators=(",",":"),sort_keys=True)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def h(p):return sha256(p.read_bytes()).hexdigest()

def build():
    path=Path(tempfile.mkdtemp(prefix="core-",dir=os.environ.get("PACKET_BUILD_DIR")))
    file=path/("core.dll" if os.name=="nt" else "core.so")
    subprocess.run(["g++","-O3","-std=c++17","-shared","-static" if os.name=="nt" else "-fPIC",str(D/"core.cpp"),"-o",str(file)],check=True)
    f=ct.CDLL(str(file)).choose
    i=ct.c_int;l=ct.c_int64;ptr=ct.POINTER
    f.argtypes=[i]*5+[ptr(i)]*3+[ptr(l)]+[ptr(i)]*2+[ptr(l)]
    f.restype=i
    return f

class Case:
    def __init__(self, data,B=2048,T=1024):
        self.c=data["cost"];self.seq=data["states"];self.B=B;self.T=T
        i,l=ct.c_int,ct.c_int64
        def pack(t,rows):return (t*len(rows))(*rows)
        ends=list(accumulate(len(r[2]) for r in self.seq))
        ids=[x for r in self.seq for x in r[2]];u=[x for r in self.seq for x in r[3]]
        assert min(self.c)>=0 and min(u,default=0)>=0
        assert all(len(set(r[2]))==len(r[2]) for r in self.seq)
        assert (sum(u)+max(u,default=0)*B)*(max(self.c,default=0)+1)<2**63
        self.ends=(i*len(ends))();self.out=(i*(len(ids)+1))();self.stats=(l*(8*len(ends)))()
        self.args=(len(self.c),len(ends),B,T)
        self.cols=(pack(i,ends),pack(i,ids),pack(i,self.c),pack(l,u),self.ends,self.out,self.stats)
    def run(self,fn,mode):
        t=perf_counter_ns()
        n=fn(*self.args,mode,*self.cols)
        elapsed=perf_counter_ns()-t
        assert n>=0
        data=ct.string_at(self.out,n*ct.sizeof(ct.c_int))+bytes(self.ends)
        return elapsed,data
    def copy(self):
        ends=[0,*self.ends]
        return [list(self.out[ends[i]:ends[i+1]]) for i in range(len(ends)-1)]

def micro(fn):
    rng=random.Random(49841);checks=0
    for _ in range(500):
        n=rng.randint(1,9);cost=[rng.randrange(0,7) for i in range(n)]
        b=rng.randrange(0,12);t=rng.randrange(b+1);states=[];all_ids=list(range(n))
        for group in range(1,4):
            k=min(n,(group*n+2)//3);ids=all_ids[:k];rng.shuffle(ids);values=[rng.randint(0,6) for _ in ids]
            used=0;j=0;head=[]
            while j<k and used+cost[ids[j]]<=t:
                used+=cost[ids[j]];head.append(ids[j]);j+=1
            tail=ids[j:];best=(0,0)
            for mask in range(1<<len(tail)):
                ii=[l for l in range(len(tail)) if mask>>l&1]
                if sum(cost[tail[l]] for l in ii)+used<=b:
                    best=max(best,(sum(values[j+l] for l in ii),-mask))
            states.append([group,group,ids,values,head+[x for l,x in enumerate(tail) if (-best[1])>>l&1]])
        case=Case({"cost":cost,"states":states},b,t)
        for mode in range(4):
            case.run(fn,mode);assert case.copy()==[r[-1] for r in states];checks+=len(states)
    return checks
def main():
    assert h(D/"PROTOCOL_RU.md")=="35e2edc293a43a03fd30456f79015d8e67a63187ae1229f029243df7ab28354c"
    fn=build();checks=micro(fn);seals={};different={};rng=random.Random(49842)
    for seed in (13,17,29,37,41):
        src=S/f"input-{seed}.json.gz"
        assert h(src)==read(S/f"sources-{seed}.json")["input"];seals[seed]=h(src)
        inp=read(src);cases={q:Case(v) for q,v in inp.items()}
        times=[];ops={};mismatches=[];identity={}
        for rep in range(6):
            qs=list(cases);rng.shuffle(qs)
            for q in qs:
                modes=list(range(4));rng.shuffle(modes)
                case=cases[q]
                for m in modes:
                    dt,bits=case.run(fn,m)
                    if q not in identity:identity[q]=bits
                    else:assert identity[q]==bits,(seed,q,m)
                    if rep:times.append([q,rep,m,dt])
                    else:
                        ops.setdefault(q,{})[m]=list(case.stats)
                        if m==0:
                            for published,chosen in zip(case.seq,case.copy()):
                                if chosen!=published[-1]:mismatches.append([q,published[0],chosen,published[-1]])
        assert len(times)==40000
        write(D/f"timing-{seed}.json.gz",times)
        write(D/f"work-{seed}.json.gz",ops)
        different[seed]=mismatches
        print("seed",seed,"mismatches vs original",len(mismatches),flush=True)
    write(D/"forecast-seal.json",dict(protocol=h(D/"PROTOCOL_RU.md"),source=h(D/"core.cpp"),input=seals,
        different=different,exhaustive=checks,payload={p.name:h(p) for p in sorted(D.glob("*.json.gz"))}))
if __name__=="__main__":main()
