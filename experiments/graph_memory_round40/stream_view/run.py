"""Replay observed message order with the three specified CPU planners."""
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import sqlite3
import numpy as np

D=Path(__file__).resolve().parent
R39=D.parents[1]/"graph_memory_round39"
def sha(data): return hashlib.sha256(data).hexdigest()
def store(name,v):
    b=(json.dumps(v,sort_keys=True,separators=(",",":"))+"\n").encode()
    (D/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith(".gz") else b)

lib=ctypes.CDLL(str(os.environ.get("STREAM_VIEW_LIBRARY") or D/("stream.dll" if os.name=="nt" else "stream.so")))
arr=lambda typ:np.ctypeslib.ndpointer(dtype=typ,flags="C_CONTIGUOUS")
lib.replay.argtypes=[ctypes.c_int]*3+[arr(np.int32),arr(np.int64),arr(np.int32),ctypes.c_int,arr(np.uint64),arr(np.int64)]
lib.replay.restype=None


def replay(c,v,at,mode,b):
    steps=int(at.max())+1
    out=np.zeros((steps,(len(c)+63)//64),dtype=np.uint64)
    stats=np.zeros(3,dtype=np.int64)
    lib.replay(len(c),steps,b,c,v,at,mode,out,stats)
    return out,stats.tolist()


def brute(c,v,at,budget):
    out=[]
    for j in range(max(at)+1):
        ids=[i for i,s in enumerate(at) if s<=j]
        head=[];used=0
        for i in ids:
            if used+c[i]>budget//2:break
            head.append(i);used+=c[i]
        tail=ids[len(head):]
        feasible=[[(tail[i]) for i in range(len(tail)) if mask>>i&1] for mask in range(1<<len(tail))]
        winner=max((sum(v[i] for i in sub),-sum(1<<i for i in sub)) for sub in feasible if used+sum(c[i] for i in sub)<=budget)
        out.append(sum(1<<i for i in head)-winner[1])
    return out


def fixtures():
    rng=random.Random(405311);steps=checks=0
    for _ in range(650):
        n=rng.randint(1,10);nb=rng.randint(1,6)
        c=np.array([rng.randint(1,12) for _ in range(n)],np.int32)
        v=np.array([rng.randint(0,7) for _ in range(n)],np.int64)
        at=np.array([rng.randrange(nb) for _ in range(n)],np.int32)
        b=rng.randint(1,26)
        oracle=brute(c.tolist(),v.tolist(),at.tolist(),b)
        for mode in range(3):
            result,_=replay(c,v,at,mode,b)
            assert result[:,0].tolist()==oracle
            checks+=len(oracle)
        steps+=len(oracle)
    return dict(pools=650,steps=steps,checks=checks)


def prepare(db,q):
    rows=db.execute("select id,tokens,utility from node where q=? order by rank",(q,)).fetchall()
    idx={r[0]:i for i,r in enumerate(rows)}
    c=np.array([r[1] for r in rows],np.int32);v=np.array([round(r[2]*2**32) for r in rows],np.int64)
    assert min(c)>0 and min(v)>=0 and sum(map(int,v))<2**63
    origins=[set() for _ in rows]
    for unit,pos in db.execute("select distinct s.id,o.position from span s join origin o on s.q=o.q and s.source=o.source where s.q=?",(q,)):
        origins[idx[unit]].add(pos)
    assert all(origins)
    distinct=sorted(set.union(*origins))
    out={}
    for condition,sequence in [("chronological",distinct),("shuffle",sorted(distinct,key=lambda pos:sha(f"r40-stream|{q}|{pos}".encode())))]:
        order={p:j for j,p in enumerate(sequence)}
        out[condition]=np.array([max(order[p] for p in origin) for origin in origins],np.int32)
    return c,v,out


def main():
    p=R39/"provenance_packet_demo/reader.sqlite"
    manifest=json.loads((p.parent/"manifest.json").read_bytes())
    assert sha(p.read_bytes())==manifest.get("files",manifest)["reader.sqlite"]
    db=sqlite3.connect(p.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    qs=[r[0] for r in db.execute("select distinct q from node order by q")]
    assert len(qs)==40
    rows={};selections={}
    for qi,q in enumerate(qs):
        c,v,arrivals=prepare(db,q)
        rows[q]={};selections[q]={}
        for order,at in arrivals.items():
            truth=None
            for mode in range(3):
                tensor,stats=replay(c,v,at,mode,2048)
                if truth is None:truth=tensor
                assert np.array_equal(tensor,truth)
            out={"times":[[],[],[]],"steps":len(truth),"nodes":len(c),"changed":int(np.any(np.diff(truth,axis=0),axis=1).sum())+int(truth[0].any())}
            for rep in range(5):
                for j in range(3):
                    mode=(j+rep+qi)%3
                    result,stats=replay(c,v,at,mode,2048)
                    assert np.array_equal(truth,result)
                    out["times"][mode].append(stats[0])
                    if mode==1:out["rebuilds"]=stats[1];out["peak_bytes"]=stats[2]
            rows[q][order]=out
            selections[q][order]=[[i for i in range(len(c)) if int(mask[i//64])>>(i%64)&1] for mask in truth]
        assert selections[q]["chronological"][-1]==selections[q]["shuffle"][-1]
    store("outcomes.json.gz",rows);store("packets.json.gz",selections)
    result={}
    for key in ("chronological","shuffle"):
        group=[r[key] for r in rows.values()]
        ns=np.array([[sum(t) for t in x["times"]] for x in group],dtype=np.int64)
        boot=ns[np.random.default_rng(405311).integers(0,40,(10000,40))].sum(axis=1)
        result[key]=dict(queries=len(group),steps=sum(x["steps"] for x in group),
            changed=sum(x["changed"] for x in group),rebuilds=sum(x["rebuilds"] for x in group),
            max_table_bytes=max(x["peak_bytes"] for x in group),total_ns=ns.sum(axis=0).tolist(),
            classic_over_incremental=ns.sum(axis=0)[0]/ns.sum(axis=0)[1],
            ratio_ci=np.quantile(boot[:,0]/boot[:,1],[.025,.975]).tolist(),
            rebuilt_over_incremental=ns.sum(axis=0)[2]/ns.sum(axis=0)[1],
            second_ci=np.quantile(boot[:,2]/boot[:,1],[.025,.975]).tolist())
    store("results.json",dict(groups=result,fixtures=fixtures(),source=sha(p.read_bytes()),
                            outcomes=sha((D/"outcomes.json.gz").read_bytes()),packets=sha((D/"packets.json.gz").read_bytes())))
    print(result)

if __name__=="__main__":
    main()

