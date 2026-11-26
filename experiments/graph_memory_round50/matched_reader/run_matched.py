"""Time 20,000 actual reader cases. Save predictions and check every historical ordered output."""
import ctypes as ct
import gzip
import os
import random
import sys
from pathlib import Path
from time import perf_counter_ns
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
import numpy as np
from common import D,W,SEEDS,MODES,sha,put,read
from runtime import Reader,arrays
def select(fn,mode,checkpoint,p,u):
    n=len(p["costs"])
    out=np.empty(n,np.int32)
    k=fn(n,mode,checkpoint,p["order"].ctypes.data,p["costs"].ctypes.data,0 if u is None else u.ctypes.data,out.ctypes.data)
    assert k>=0
    return out[:k].tolist()
def main():
    assert sha(D/"PROTOCOL_RU.md")=="8127a24dc5fe7119490ef3d6831d41fd62de88e5c2a2dacfa5be559d28105a11"
    pool=read(D/"pool.json.gz")
    reader=Reader();fn=reader.lib.packet
    fn.argtypes=[ct.c_int]*3+[ct.c_void_p]*4;fn.restype=ct.c_int
    receipts={}
    for seed in map(int,sys.argv[1:] or SEEDS):
        ranks=read(D/f"ranks-{seed}.json.gz")
        fp=D/f"utility-{seed}.f64.gz"
        assert sha(fp)==read(D/"original_receipt.json")[str(seed)]["utility"]
        vec=np.frombuffer(gzip.decompress(fp.read_bytes()),dtype="<f8")
        cases={};offset=0
        for q,r in sorted(pool.items()):
            dense,*orders=ranks[q]
            p=arrays(dict(z=r["x"],offset=r["o"],costs=r["c"],dense=dense,order=orders[0],seed=seed))
            p1=dict(p,order=np.array(orders[1],dtype=np.int32))
            n=len(p["costs"]);v=vec[offset:offset+n];offset+=n
            assert np.array_equal(v,reader.utility(reader.features(p)))
            assert (v.max()*2**32+1)*n*max(int(p["costs"].max()),2048)*4<2**63
            cases[q]=(p,p1,v)
        assert offset==len(vec)
        rng=random.Random(50419+seed);forecasts={};times={}
        for rep in range(4):
            order=list(cases);rng.shuffle(order)
            for q in order:
                pair=list(range(2));rng.shuffle(pair)
                for cp in pair:
                    p=cases[q][cp];v=cases[q][2]
                    modes=list(range(5));rng.shuffle(modes)
                    for m in modes:
                        # Separate physical timings use the frozen utility versus a complete fresh tree pass.
                        # The modes and order of these two paths are randomized within each case.
                        paths=[0,1];rng.shuffle(paths)
                        for path in paths:
                            start=perf_counter_ns()
                            if m==3:u=None
                            elif path:u=reader.utility(reader.features(p))
                            else:u=v
                            ids=select(fn,m,cp,p,u)
                            elapsed=perf_counter_ns()-start
                            if rep:times[q][cp][m][path].append(elapsed)
                            else:
                                if q not in forecasts:
                                    forecasts[q]=[[None]*5 for _ in range(2)]
                                    times[q]=[[[[],[]] for _ in range(5)] for _ in range(2)]
                                old=forecasts[q][cp][m]
                                if old is None:forecasts[q][cp][m]=ids
                                else:assert old==ids
                            assert forecasts[q][cp][m]==ids
        put(D/f"predictions-{seed}.json.gz",forecasts)
        put(D/f"times-{seed}.json.gz",times)
        arch=read(D/f"archive-{seed}.json.gz")
        counts=[0,0]
        for q in cases:
            for cp in (0,1):
                dp,ff,val=arch[q][cp]
                expected=[dp,dp,dp,ff,val]
                assert forecasts[q][cp]==expected,(q,cp,seed,[(i,len(g),len(e)) for i,(g,e) in enumerate(zip(forecasts[q][cp],expected)) if g!=e])
                counts[cp]+=5
        receipts[seed]={"matches":counts,"plans":list(MODES),"candidates":offset,"times":sha(D/f"times-{seed}.json.gz"),"predictions":sha(D/f"predictions-{seed}.json.gz"),"archive":sha(D/f"archive-{seed}.json.gz")}
        put(D/f"forecast-{seed}.json",receipts[seed])
        print("checked quality-blind packets and both timing paths",seed,counts,flush=True)
if __name__=="__main__":main()

