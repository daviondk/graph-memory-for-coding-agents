"""All model choices are fixed. This program reads no evaluation labels."""
import ctypes
import os
import sys
from time import perf_counter
from shared import D,W,CURVE,GLOBAL,REMAIN,SEEDS,BUDGETS,ORDERS,RULES,read,save,sha,log
import predict as curve
packet=curve.packet
np=packet.np
from pathlib import Path
DLL=Path(os.getenv("R39_EXACT_FILL_DLL",str(W.parent/"tmp/r39-hybrid-exact.dll")))


def exact_solver():
    lib=ctypes.CDLL(str(DLL))
    fn=lib.choose_exact
    ptr=np.ctypeslib.ndpointer
    fn.argtypes=[ctypes.c_int,ctypes.c_int]+[ptr(dtype=d,ndim=1,flags="C_CONTIGUOUS") for d in (np.int32,np.float64,np.uint8)]
    fn.restype=ctypes.c_int
    def choose(c,u,b):
        found=np.zeros(len(c),np.uint8)
        feasible=fn(len(c),b,np.ascontiguousarray(c,dtype=np.int32),np.ascontiguousarray(u,dtype=float),found)
        assert feasible
        return np.flatnonzero(found)
    return choose


def candidates(order,c,ug,ud,b,solve,exact,known):
    total=np.cumsum(c[order])
    k=int(total.searchsorted(b//2,side="right"))
    head=order[:k].tolist()
    remain=b-(int(total[k-1]) if k else 0)
    tail=order[k:]
    pos=np.flatnonzero(c[tail]<=remain)
    ids=tail[pos]
    costs=c[ids];g=ug[ids]
    def arr(indices):
        return head+ids[indices].tolist()
    strict,ff,old_dp=known
    picked_dp=arr(solve(costs,g,remain))
    assert old_dp==picked_dp and strict[:k]==ff[:k]==head
    idx_density=np.asarray(packet.base.fill(costs,np.argsort(-g/costs,kind="stable"),remain),dtype=int)
    idx_value=np.asarray(packet.base.fill(costs,np.argsort(-g,kind="stable"),remain),dtype=int)
    greedy_spend=int(costs[idx_density].sum())
    idx_exact=exact(costs,g,greedy_spend)
    equal=arr(idx_exact)
    density=arr(idx_density)
    assert int(costs[idx_exact].sum())==greedy_spend and g[idx_exact].sum()+1e-10>=g[idx_density].sum()
    return [strict,ff,picked_dp,density,arr(idx_value),arr(solve(costs,np.log1p(1/(pos+1)),remain)),
            arr(solve(costs,ud[ids],remain)),equal]


def forecast(seed):
    start=perf_counter()
    dst=D/f"test-{seed}-packets.json.gz";seal=D/f"test-{seed}-seal.json"
    if seal.exists():
        assert sha(dst)==read(seal)["packets"]
        return
    assert sha(D/"PROTOCOL_RU.md")=="15c2e56701ac27720e9d5bbb70bd4f9785ba4f9cc2f3c680a613a2de436188bc"
    curve_seal=read(CURVE/f"test-{seed}-seal.json")
    source=CURVE/f"test-{seed}-packets.json.gz"
    assert sha(source)==curve_seal["packets"] and sha(GLOBAL/"models.json")==curve_seal["model"]
    existing=read(source)
    native,receipts=curve.native_ranks(seed)
    reg,x=packet.projections("test",seed)
    models=read(GLOBAL/"models.json")["models"]
    utilities=[np.logaddexp(0,packet.portable(models[n],x[:,models[n]["cols"]])) for n in ("graph","dense")]
    solve,exact=packet.base.kernel(),exact_solver()
    assert set(reg)==set(existing)==set(native)
    rows={}
    for q,(t,c,r35,_,sl) in reg.items():
        assert existing[q][0]==t
        arms=[]
        for i,name in enumerate(ORDERS):
            order=np.asarray(native[q][name],dtype=int)
            arms.append([candidates(order,c,utilities[0][sl],utilities[1][sl],b,solve,exact,existing[q][1][i+1][j])
                         for j,b in enumerate(BUDGETS)])
        rows[q]=[t,arms]
    save(dst,rows)
    save(seal,dict(packets=sha(dst),models=curve_seal["model"],native_seals=receipts,registered=sha(D/"PROTOCOL_RU.md"),
        implementation=sha(D/"forecast.py"),kernel_source=sha(D/"exact_fill.cpp"),kernel_binary=sha(DLL),
        shared=sha(D/"shared.py"),orders=ORDERS,rules=RULES,budgets=BUDGETS,source_packets=sha(source),
        graph_dp_matches=2000*len(ORDERS)*len(BUDGETS),seed=seed,rows=len(rows)))
    log("frozen",seed=seed,seconds=round(perf_counter()-start,3),sha256=sha(dst))
    print("Frozen",seed,sha(dst),flush=True)


if __name__=="__main__":
    for seed in map(int,sys.argv[1:] or SEEDS):
        forecast(seed)
