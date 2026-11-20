"""Post-hoc targeted ablation giving the conventional cache short block tags and strong response validation."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import numpy as np
from codec import Reader,compact,hashmsg,ids,loc,lp,offers,readloc,spans,uint,unpack,request,whole_frame
from delta import canonical
from experiment import D,archive,dec,enc,locations,mem,post,read,rows,write
from optimistic import strong

def req(path,vr,memory,mode,width):
    s={n:v[0] for n,v in memory.items()}
    groups=offers(memory,vr,mode)
    if not groups:return request(path,vr,{},"full")
    raw=bytearray(lp(path.encode())+uint(int(vr is not None)))
    if vr is not None:raw.extend(uint(vr[0])+uint(vr[1]+1))
    raw.extend(uint(4 if width==1 else 5)+uint(len(groups)))
    for group in groups:raw.extend(loc(group)+hashmsg(s,group)[:width])
    return compact(bytes(raw))
def extract(req):
    r=Reader(unpack(req));r.string()
    if r.num():r.num();r.num()
    typ=r.num()
    if typ==0:assert r.num()==0;return []
    width={4:1,5:4}[typ]
    groups=[(readloc(r),r.take(width)) for _ in range(r.num())]
    assert r.i==len(r.raw)
    return groups
def serve(req,target,full,canonical_bytes):
    groups=extract(req);mask=0;used=set()
    for j,(seg,tag) in enumerate(groups):
        ns=set(ids(seg))
        if ns<=target.keys() and hashmsg(target,seg)[:len(tag)]==tag:used.update(ns);mask|=1<<j
    if not used:return full
    geo=spans(target)
    raw=loc(geo)+strong(canonical_bytes)+mask.to_bytes((len(groups)+7)//8,"little")+b"".join(lp(target[n]) for n in ids(geo) if n not in used)
    delta=b"S"+compact(raw)
    return delta if len(delta)<len(full) else full
def receive(req,rep,cache):
    r=Reader(unpack(rep[1:]));geo=readloc(r);gs=extract(req);used=set();h=None
    if rep[:1]==b"S":
        h=r.take(16);mask=int.from_bytes(r.take((len(gs)+7)//8),"little")
        for j,(seg,tag) in enumerate(gs):
            if mask&(1<<j):used.update(ids(seg))
    actual={n:(cache[n][0] if n in used else r.string()) for n in ids(geo)}
    assert r.i==len(r.raw)
    return actual if h is None or strong(canonical(actual))==h else None
def one(job):
    p,j=job
    inp,truth,*_=locations(p,j)
    with archive(D/f"short_cost_{p}_{j}.jsonl.gz","w") as out:
        for x,y,aux in zip(rows(inp),rows(truth),rows(D/f"opt_cost_{p}_{j}.jsonl.gz"),strict=True):
            issue,repo,t,path,vr,blobs=x;assert (issue,t)==(y[0],y[1])==(aux[0],aux[2])
            m=mem(blobs["lru"],path,vr);tar={n:v.encode() for n,v in y[2]};raw=canonical(tar);full=whole_frame(tar);get=request(path,vr,{},"full")
            dst={}
            for mode,width in product(("pages","runs"),(1,4)):
                f=req(path,vr,m,mode,width);g=serve(f,tar,full,raw);a=receive(f,g,m);retry=0
                if a is None:retry=1;a=receive(get,full,{})
                assert a==tar
                dst[mode+str(width)]=[len(f)+len(g)+retry*(len(get)+len(full)),retry]
            post(out,[issue,repo,t,aux[3]["optim"][0],dst])
if __name__=="__main__":
    with ProcessPoolExecutor(4) as ex:list(ex.map(one,[(p,i) for p in "ABC" for i in range(8)]))
    summary={}
    for p in "ABC":
        arr=[r for j in range(8) for r in rows(D/f"short_cost_{p}_{j}.jsonl.gz")]
        labs=np.array([r[1] for r in arr]);cl=[labs==k for k in sorted(set(labs))];nn=np.array([c.sum() for c in cl]);ix=np.random.default_rng(184296).integers(len(cl),size=(10000,len(cl)))
        comp={}
        for name in arr[0][-1]:
            x=np.array([r[-1][name][0] for r in arr]);d=x-np.array([r[3] for r in arr]);cs=np.array([d[c].sum() for c in cl]);b=cs[ix].sum(axis=1)/nn[ix].sum(axis=1)
            comp[name]=dict(n=len(arr),bytes=int(x.sum()),retry=sum(r[-1][name][1] for r in arr),optim_savings=int(d.sum()),percent=float(100*d.sum()/x.sum()),per_view=float(d.mean()),ci=np.quantile(b,[.025,.975]).tolist())
        summary[p]=comp
    write(D/"short_results.json",summary);print(summary)

