"""Paired latency against the cheaper Dense first-fit reader, which produces different packets."""
import os
import random
import subprocess
import tempfile
from collections import defaultdict
from statistics import median
from pathlib import Path
from run import bench,D,S,digest,load,save

def main():
    import numpy as np
    source=load(S/"input.json.gz")
    ranks=load(S/"packets.json.gz")
    exact=load(D/"packets.json.gz")
    fn=bench.library()
    # Keep the same C type contract as the primary kernel. Only the selected top-level entry point changes.
    with tempfile.TemporaryDirectory(dir=os.environ.get("PACKET_BUILD_DIR")) as tmp:
        so=Path(tmp)/("direct.dll" if os.name=="nt" else "direct.so")
        subprocess.run(["g++","-std=c++17","-O3","-shared","-static" if os.name=="nt" else "-fPIC",str(D/"direct_control.cpp"),"-o",str(so)],check=True)
        lib=bench.ct.CDLL(str(so))
        fn2=lib.serve
        fn2.argtypes=fn.argtypes;fn2.restype=fn.restype
        cases={q:bench.Input(u,e) for q,(_,u,e) in source.items()}
        timings=[];rng=random.Random(49172)
        for rep in range(6):
            order=list(cases);rng.shuffle(order)
            for q in order:
                modes=[16,101];rng.shuffle(modes)
                for mode in modes:
                    t,stats,ids,ends=cases[q].trial(fn2,mode,1,0)
                    if rep:timings.append([q,rep,mode,t])
                    else:
                        packs=cases[q].packs(ids,ends); s=cases[q]
                        for step in {8,s.st}:
                            if step>s.st:continue
                            expected=exact[q]["0"][str(step)] if mode==16 else ranks[q][str(step)]["dense"]
                            assert packs[step-1]==expected
                        if mode==101:
                            for step,arr in enumerate(packs,1):
                                remaining=2048;expected=[]
                                for b,i,c,v,a in sorted(s.items,key=lambda r:r[1]):
                                    if b<=step and c<=remaining:
                                        remaining-=c;expected.append(i)
                                assert arr==expected
        if os.name=="nt":
            # An opened DLL remains locked until it is unloaded.
            import _ctypes
            _ctypes.FreeLibrary(lib._handle)
    save(D/"direct-timing.json.gz",timings)
    samples=defaultdict(list)
    for q,rep,mode,t in timings:samples[q,mode].append(t)
    groups={tr:i for i,tr in enumerate(sorted({r[0] for r in source.values()}))}
    m=np.zeros((len(groups),2))
    for q,(tr,_,_) in source.items():
        for j,mode in enumerate((101,16)):m[groups[tr],j]+=median(samples[q,mode])
    totals=m.sum(axis=0)/1e6
    gen=np.random.default_rng(49172)
    weight=gen.multinomial(len(m),np.full(len(m),1/len(m)),size=10000).astype(float)
    a=weight@m
    out=dict(dense_ms=totals[0],exact_ms=totals[1],ratio=totals[1]/totals[0],
        ci=np.percentile(a[:,1]/a[:,0],[2.5,97.5]).tolist(),trials=len(timings))
    save(D/"direct-results.json",out);print(out)
if __name__=="__main__":main()
