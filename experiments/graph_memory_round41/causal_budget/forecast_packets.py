"""Rank at each cut using fixed training-only weights and current graph features."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):os.environ[key]="1"
import numpy as np
D=Path(__file__).resolve().parent
W=D.parents[1];R39=W/"graph_memory_round39"
sys.path.insert(0,str(R39/"global_packet"))
import packet
from packet import read,sha,save


def firstfit(order,c,budget):
    used=0;out=[]
    for i in order:
        if used+int(c[i])<=budget:
            out.append(int(i));used+=int(c[i])
    return out


def forecast(seed,shards):
    original={r["q"]:r for r in read(Path("D:/CodexResearch/x20-r33-budget-loss/test.json.gz"))}
    gp=R39/"global_packet"
    m=read(gp/"models.json")["models"]["graph"]
    ref=read(gp/f"test-{seed}-pred.json.gz")
    model=read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"] if seed==13 else read(W/f"graph_memory_round21/five_seed/seed-{seed}/calibration.json")["rank"]
    solve=packet.base.kernel()
    for sh in shards:
        source=D/f"state-{sh}.json.gz"; lock=read(D/f"state-{sh}-seal.json")
        assert sha(source)==lock["data"]
        frozen=read(source);allx=[];rows=[]
        orders={} if seed==13 else {r["q"]:r["dense"] for r in read(W/f"graph_memory_round21/five_seed/seed-{seed}/picks-{sh}.json.gz")}
        for q,t,pct,at,visible,graph,pilot in frozen:
            ids=np.asarray(visible,dtype=int); n=len(ids); raw=original[q];assert raw["t"]==t
            z=np.array(raw["x"])[ids].copy()
            locations={j:i for i,j in enumerate(visible)}
            dense=np.arange(n) if seed==13 else np.array([locations[j] for j in orders[q] if j in locations],dtype=int)
            assert len(dense)==n
            offset=np.empty(n)
            offset[dense]=packet.base.linear(model,packet.base.rankx(n))
            z[dense,0]=np.log1p(np.arange(1,n+1))
            x,rank=packet.feature(z,np.asarray(graph),offset)
            rows.append((q,t,pct,at,ids,dense,rank,np.asarray(raw["c"],dtype=int)[ids],pilot))
            allx.append(x)
        u=np.logaddexp(0,packet.portable(m,np.vstack(allx)[:,m["cols"]]))
        pos=0;results=[];terminal=0
        for q,t,pct,at,ids,dense,rank,c,pilot in rows:
            gain=u[pos:pos+len(ids)];pos+=len(ids)
            head=int(c[rank].cumsum().searchsorted(2048,side="right"))
            choices={
                "graph_dp":packet.select(rank,c,gain,1024,"dp",solve),
                "graph_firstfit":firstfit(rank,c,2048),
                "graph_strict":rank[:head].tolist(),
                "dense_firstfit":firstfit(dense,c,2048)}
            shown={k:ids[v].tolist() for k,v in choices.items()}
            assert all(c[v].sum()<=2048 and len(set(v))==len(v) for v in choices.values())
            if pct==100:
                assert shown["graph_dp"]==ref[q][1]["graph-dp"] and shown["graph_firstfit"]==ref[q][1]["R35-firstfit"],(q,seed)
                terminal+=1
            results.append([q,t,pct,pilot,shown])
        assert pos==len(u)
        out=D/f"pred-{seed}-{sh}.json.gz"
        save(out,results)
        save(D/f"pred-{seed}-{sh}-seal.json",dict(data=sha(out),inputs=sha(source),model=sha(gp/"models.json"),protocol=lock["protocol"],terminal=terminal,rows=len(rows),code=sha(Path(__file__))))
        print(seed,sh,terminal,flush=True)


if __name__=="__main__":
    s=int(sys.argv[1])
    forecast(s,[int(x) for x in sys.argv[2:]] or range(8))

