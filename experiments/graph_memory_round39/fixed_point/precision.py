"""Integer-valued exact planner and cross-check of benchmark and source-withdrawal snapshots."""
from pathlib import Path
import ctypes
import hashlib
import os
import struct
import sys
D=Path(__file__).resolve().parent;GLOBAL=D.parent/"global_packet";sys.path.insert(0,str(GLOBAL))
from packet import base,projections,portable,read,save,sha,np,select,THRESHOLDS
SEEDS=(13,17,29,37,41);BITS=(8,16,32)
def solver():
    lib=ctypes.CDLL(os.getenv("R39_KNAPSACK_INT_DLL","D:/CodexResearch/x20-bench-workspace/tmp/r39-integer.dll"))
    fn=lib.choose64;fn.argtypes=[ctypes.c_int,ctypes.c_int]+[np.ctypeslib.ndpointer(dtype=d,flags="C_CONTIGUOUS",ndim=1) for d in (np.int32,np.int64,np.uint8)]
    fn.restype=None
    def solve(cost,gains,capacity):
        x=np.ascontiguousarray(gains,dtype=np.int64);c=np.ascontiguousarray(cost,dtype=np.int32)
        out=np.empty(len(c),dtype=np.uint8)
        fn(len(c),capacity,c,x,out)
        return np.flatnonzero(out)
    return solve
def quantize(u,b):
    z=np.rint(u*(2**b));assert np.isfinite(z).all() and z.min()>=0 and int(z.max())*len(z)<(1<<63)
    return z.astype(np.int64)
def forecast():
    m=read(GLOBAL/"models.json")["models"]["graph"];T=read(GLOBAL/"dev-selection.json")["thresholds"]["graph"];assert T==1024
    solve=solver();checks=0;rng=np.random.default_rng(390091)
    for _ in range(100):
        c=rng.integers(1,10,8);u=rng.integers(0,5,8,dtype=np.int64);cap=int(rng.integers(0,35));masks=np.arange(256)
        flags=masks[:,None]>>np.arange(8)&1;selected=solve(c,u,cap);valid=masks[flags@c<=cap]
        best=int(valid[np.argmax((flags@u)[valid])]);assert best==sum(1<<int(x) for x in selected);checks+=1
    pnames={}
    for seed in SEEDS:
        reg,x=projections("test",seed);raw=np.logaddexp(0,portable(m,x[:,m["cols"]]));pred={};bound={str(b):0 for b in BITS}
        for q,(t,c,order,_,sl) in reg.items():
            outputs={}
            for b in BITS:
                u=quantize(raw[sl],b);bound[str(b)]=max(bound[str(b)],int(u.sum()))
                outputs[str(b)]=select(order,c,u,T,"dp",solve)
            pred[q]=[t,outputs]
        p=D/f"test-{seed}-pred.json.gz";save(p,pred);pnames[str(seed)]=dict(sha=sha(p),max_utility_sum=bound)
    save(D/"seal.json",dict(rows=2000,seeds=pnames,model=sha(GLOBAL/"models.json"),dev=sha(GLOBAL/"dev-selection.json"),protocol=sha(D/"PROTOCOL_RU.md"),cpp=sha(D/"integer.cpp"),code=sha(Path(__file__)),brute=checks))
    print("frozen",pnames,flush=True)
def evaluate():
    receipt=read(D/"seal.json")
    sys.path.insert(0,str(base.W/"graph_memory_round33/budget_loss"));import data as upstream
    refs=read(upstream.nm.OFF/"gold-spans.json.gz")
    exact={}
    for seed in SEEDS:
        p=D/f"test-{seed}-pred.json.gz";assert receipt["seeds"][str(seed)]["sha"]==sha(p)
        packets=read(p);original=read(GLOBAL/f"test-{seed}-pred.json.gz")
        old=read(GLOBAL/f"test-{seed}-outcomes.json.gz");diff={};stats={str(b):dict(changed=0,won=0,lost=0,coverage_delta=0.) for b in BITS}
        for src in upstream.sources("test"):
            for r in read(src):
                q=r["q"];known=old[q][1]["graph-dp"];cache={}
                for b in BITS:
                    key=str(b);ids=packets[q][1][key]
                    if ids==original[q][1]["graph-dp"]:continue
                    rs=stats[key];rs["changed"]+=1
                    if tuple(ids) not in cache:
                        g=tuple(upstream.nm.pilot.SourceSpan.model_validate(s) for s in refs[q])
                        nodes=tuple(upstream.nm.pilot.RankedNodeRecord.model_validate(r["rr"][i]) for i in ids)
                        v=upstream.nm.pilot.span_metrics_under_token_budget(nodes,g,2048);cache[tuple(ids)]=[v.full_support,v.coverage]
                    a=cache[tuple(ids)];rs["won"]+=int(a[0]>known[0]);rs["lost"]+=int(a[0]<known[0])
                    rs["coverage_delta"]+=a[1]-known[1];diff.setdefault(q,{})[key]=a
        save(D/f"changes-{seed}.json.gz",diff);exact[str(seed)]=stats
    save(D/"benchmark.json",dict(seeds=exact,rows=10000,seal=sha(D/"seal.json")))
    print(exact,flush=True)
def withdrawals():
    root=D.parent/"exact_certificate";sys.path.insert(0,str(root))
    from test_certificate import bits,unchanged,Snapshot,DEMO
    d=Snapshot(DEMO/"reader.sqlite");schedule=read(root/"schedule.json.gz");before=read(root/"outcomes.json.gz");solve=solver()
    v={};total=same=unchanged_n=0
    for q,o in schedule.items():
        rows=d.rows(q,None);ids=np.array([r[0] for r in rows]);c=np.array([r[1] for r in rows])
        u=quantize(np.array([r[2] for r in rows]),32);integer=[(int(i),int(cost),int(val)) for i,cost,val in zip(ids,c,u)]
        def pack(filtered):
            cs=np.asarray([r[1] for r in filtered],dtype=np.int32);us=np.asarray([r[2] for r in filtered],dtype=np.int64);ii=np.asarray([r[0] for r in filtered],dtype=int)
            cum=cs.cumsum();n=int(np.searchsorted(cum,1024,side="right"));cap=2048-(int(cum[n-1]) if n else 0);ix=n+np.flatnonzero(cs[n:]<=cap)
            return tuple(int(x) for x in np.r_[ii[:n],ii[ix[solve(cs[ix],us[ix],cap)]]]),(0 if n==len(ii) else 1<<int(ii[n]))
        old,barrier=pack(integer);oldbits=bits(old)
        groups={s:0 for s in o["sources"]}
        for uid,s in d.conn.execute("SELECT DISTINCT id,source FROM span WHERE q=?",(q,)):groups[s]|=1<<uid
        masks=[groups[s] for s in o["sources"]];by={}
        for k,items in o["sets"].items():
            count=0;ok=0
            for j,pick in enumerate(items):
                z=0
                for i in pick:z|=masks[i]
                arr,_=pack([r for r in integer if not z&(1<<r[0])]);truth=old==arr;assert truth==unchanged(z,oldbits,barrier,integer,2048)
                h=hashlib.sha256(struct.pack("<"+"I"*len(arr),*arr)).hexdigest()
                ok+=h==before[q][k][j][4];count+=truth
            total+=len(items);same+=ok;unchanged_n+=count;by[k]=[len(items),ok,count]
        v[q]=by
    save(D/"withdrawals.json",dict(total=total,float_same=same,certified_unchanged=unchanged_n,rows=v,schedule=sha(root/"schedule.json.gz"),float_outputs=sha(root/"outcomes.json.gz")))
    print(total,same,unchanged_n)
if __name__=="__main__":
    {"forecast":forecast,"score":evaluate,"withdraw":withdrawals}[sys.argv[1]]()

