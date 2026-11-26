"""Adversarial tie/budget cases and trajectory-cluster uncertainty from archived request rows."""
import hashlib
from collections import defaultdict
import numpy as np
from layers import exact,Index,prefix
from lossless import pack,Head,batch
from run import HERE,put,read

def exercise(values,order,signal,costs):
    wanted=prefix(order[np.argsort(-(signal+values[order]),kind="stable")],costs)
    checks=0
    for dictionary in (True,False):
        hot,cold=pack(values,dictionary);head=Head(hot)
        assert len(head.top)==len(values) and all(head.lo<=values) and all(values<=head.hi)
        def one(i):return head.recover(i,cold[5*i:5*i+5])
        assert np.array([one(i) for i in range(len(values))]).tobytes()==values.tobytes()
        def fetch(ids):return {int(i):cold[5*i:5*i+5] for i in ids}
        actual,_=batch(head,order,signal,costs,fetch)
        sequential,_=exact("lossless",head,order,signal,costs,None,one)
        assert wanted==actual==sequential
        checks+=2
    return wanted,checks

def main():
    rng=np.random.default_rng(73017);checks=0;hotchecks=0
    for rep in range(2500):
        n=[0,1,2,3,8,17,48,91][rep%8]
        case=rep%7
        if case==0: v=rng.choice(np.asarray([0.,-0.,1.,-1.,np.nextafter(0.,1.),np.nextafter(0.,-1.)]),n)
        elif case==1: v=1.+rng.integers(-10,10,n).astype(float)*2**-40
        elif case==2: v=np.ldexp(rng.choice([-1.,1.],n),rng.integers(-50,5,n))
        elif case==3: v=rng.integers(-2,3,n).astype(float)
        else: v=rng.normal(size=n)
        order=rng.permutation(n);s=np.zeros(n) if rep%3 else rng.normal(size=n)
        c=rng.choice([1,17,400,1024,1300,2048,2049],n)
        _,k=exercise(v,order,s,c);checks+=k
        if n:
            hot=Index(v)
            a=np.frombuffer(hot.high,dtype=np.uint8)[order//2];dec=(a>>(4*(order%2)))&15
            lo,hi=hot.interval("b4",order)
            assert np.array_equal(lo,hot.bounds[16*dec]) and np.array_equal(hi,hot.bounds[16*dec+16])
            hotchecks+=len(order)
    v=np.array([1.,1.+2.**-36]);order=np.arange(2);c=np.full(2,1300)
    wanted,_=exercise(v,order,np.zeros(2),c)
    approx=prefix(np.argsort(-v.astype(np.float32),kind="stable"),c)
    assert wanted==[1] and approx==[0]

    rows=read(HERE/"rows.json.gz");groups=defaultdict(lambda:np.zeros(4))
    for r in rows.values():
        for m in r["seeds"].values():
            a,b=m["b4"],m["b4_b8"]
            groups[r["t"]]+=np.asarray([8*a[1],b[0]+8*b[1],1.,int(a[1]!=0)])
    a=np.stack(list(groups.values()));bt=[]
    for _ in range(10000):
        x=a[rng.integers(len(a),size=len(a))].sum(axis=0)
        bt.append(100*(1-x[1]/x[0]))
    cases=defaultdict(lambda:defaultdict(list))
    for q,m,rep,elapsed,calls,nbytes,ok in read(HERE/"physical-reads.json.gz"):
        cases[q][m].append((elapsed/1000,nbytes))
    g=defaultdict(lambda:np.zeros(4))
    for q,m in cases.items():
        full,cs=[np.median(m[k],axis=0) for k in ("fp64","class_batch")]
        g[rows[q]["t"]]+=[1.,cs[0]-full[0],cs[1],full[1]]
    a=np.stack(list(g.values()));samples=[]
    for _ in range(10000):
        n,dt,cs,full=a[rng.integers(len(a),size=len(a))].sum(axis=0)
        samples.append([dt/n,100*(1-cs/full)])
    put(HERE/"audit.json",{"random_cases":2500,"exact_prefix_checks":checks,"decoded_nibbles":hotchecks,"tie_example":{"fp64":wanted,"fp32":approx,"priors":v.tolist(),"costs":c.tolist()},"clusters":len(groups),"read_reduction_ci95_pct":np.percentile(bt,[2.5,97.5]).tolist(),"sqlite_panel_questions":len(cases),"sqlite_clusters":len(g),"sqlite_intervals":{"columns":["mean_paired_per_query_median_latency_delta_us","mean_payload_reduction_pct"],"ci95":np.percentile(samples,[2.5,97.5],axis=0).tolist()}})
if __name__=="__main__":main()
