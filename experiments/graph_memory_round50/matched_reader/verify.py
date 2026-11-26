"""Verify signed files, all native ordered packets, official-grade witnesses, and paired statistics."""
import ctypes as ct
import gzip
import os
import sys
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
import numpy as np
from common import D,SEEDS,sha,read
from run_matched import select
from runtime import Reader,arrays
from stats import calculate

def main():
    files=read(D/"manifest.json")["files"]
    assert all(sha(D/n)==v for n,v in files.items())
    pool=read(D/"pool.json.gz");atoms=read(D/"test-atoms.json.gz");scores=read(D/"scores.json.gz")
    assert set(pool)==set(scores)==set(atoms) and len(scores)==2000
    model=Reader();fn=model.lib.packet;fn.argtypes=[ct.c_int]*3+[ct.c_void_p]*4;fn.restype=ct.c_int
    checked=0;chrono={}
    for si,s in enumerate(SEEDS):
        arch=read(D/f"archive-{s}.json.gz");pred=read(D/f"predictions-{s}.json.gz")
        ranks=read(D/f"ranks-{s}.json.gz");chrono[s]=read(D/f"times-{s}.json.gz")
        vec=np.frombuffer(gzip.decompress((D/f"utility-{s}.f64.gz").read_bytes()),dtype="<f8")
        off=0
        for q,row in sorted(pool.items()):
            assert scores[q][0]==row["t"]
            dense,*rr=ranks[q];n=len(row["c"]);v=vec[off:off+n];off+=n
            p=arrays(dict(z=row["x"],offset=row["o"],costs=row["c"],dense=dense,order=rr[0],seed=s))
            assert np.array_equal(model.utility(model.features(p)),v)
            truth=[(b-a,set(idx)) for _,a,b,idx in atoms[q]];total=sum(w for w,_ in truth)
            for cp,rank in enumerate(rr):
                p["order"]=np.asarray(rank,np.int32)
                dp,ff,val=arch[q][cp]
                for m,seq in enumerate((dp,dp,dp,ff,val)):
                    assert seq==pred[q][cp][m]==select(fn,m,cp,p,v)
                    ids=set(seq)
                    covered=sum(w for w,x in truth if not x.isdisjoint(ids))
                    cost=sum(row["c"][i] for i in seq)
                    g=scores[q][1][si][cp][m]
                    assert len(seq)==len(ids) and cost<=2048 and cost==g[2]
                    assert (covered==total)==g[0] and abs(covered/total-g[1])<1e-12
                    pair=chrono[s][q][cp][m]
                    assert len(pair)==2 and all(len(reps)==3 and min(reps)>0 for reps in pair)
                    checked+=1
        assert off==len(vec)
    original=read(D/"results.json")
    calc=calculate(scores,chrono)
    def check(x,y):
        if isinstance(x,dict):return x.keys()==y.keys() and all(check(x[k],y[k]) for k in x)
        if isinstance(x,list):return len(x)==len(y) and all(check(a,b) for a,b in zip(x,y))
        if isinstance(x,float):return abs(x-y)<1e-8
        return x==y
    assert check(calc,original) and checked==100000
    print("Verified",len(files),"files,",checked,"ordered ID and span results, 600000 timed endpoints, 6000 paired bootstrap draws.")
if __name__=="__main__":main()

