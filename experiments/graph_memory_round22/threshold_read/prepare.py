"""Build anonymous numeric benchmark fixtures; ranking methods never read task text in measurement."""
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
R20=WORK/"graph_memory_round20"
sys.path.insert(0,str(R20/"factor_reader"))
import factor as f
from factor import np,save,load,sha
from operators import index


def materialize():
    idx=f.gmod.graph_index();prior=f.load(f.D/"prior.json")["models"]["prior"]
    m=load(f.D/"hash64-weights.json")["rank"];start=time.perf_counter()
    seals=load(f.D/"hash64-seal.json");sums={};p=0;ts=set();qs=set()
    for i in range(8):
        ranks=f.D/f"hash64-ranks-{i}.json.gz";assert sha(ranks)==seals["files"][ranks.name]
        saved={r["q"]:r for r in load(ranks)};canon=f.app.rd.source("dense",i)
        grouped={}
        for r in load(canon):grouped.setdefault(r["t"],[]).append(r)
        trajectories=[]
        for t,rows in sorted(grouped.items()):
            assert t not in ts;ts.add(t)
            raw=load(f.app.rd.stream.CACHE/f"{i}-{t}.json.gz")
            keys,x=f.shape(raw["pool"],f.gmod.project(t,idx));at={k:j for j,k in enumerate(keys)}
            ps=f.lin(prior,x[:,prior["columns"]]);by= {r["node_id"]:r["token_count"] for r in rows[0]["rr"]}
            costs=[by[k] for k in keys];n=len(keys);p+=n
            signal=f.lin(m,f.rank_x(n));sample=[]
            for r in rows:
                q=r["q"];assert q not in qs;qs.add(q)
                rr=r["rr"];order=np.array([at[v["node_id"]] for v in rr],dtype=int)
                assert len(order)==n and all(costs[j]==v["token_count"] for j,v in zip(order,rr,strict=True))
                ord0=saved.pop(q)["ranks"]["factor"]
                found=np.argsort(-(signal+ps[order]),kind="stable")
                assert found.tolist()==ord0
                sample.append({"q":q,"order":order.tolist(),"expected":{k:list(map(int,order[f.gmod.pack(ord0,[v["token_count"] for v in rr],k=="skip")])) for k in ("prefix","skip")}})
            trajectories.append({"t":t,"prior":ps.tolist(),"costs":costs,"signal":signal.tolist(),"queries":sample})
        assert not saved
        fp=HERE/f"fixture-{i}.json.gz";save(fp,trajectories)
        sums[fp.name]={"sha":sha(fp),"original_dense":sha(canon),"factor_ranks":sha(ranks)}
    assert len(qs)==2000 and len(ts)==1207
    save(HERE/"inputs.json",{"shards":sums,"q":len(qs),"t":len(ts),"nodes":p,"weights":sha(f.D/"hash64-weights.json"),"prior":sha(f.D/"prior.json"),
              "source_seal":sha(f.D/"hash64-seal.json"),"protocol":sha(HERE/"PROTOCOL_RU.md"),"code":sha(Path(__file__)),"materialization_seconds":time.perf_counter()-start})


if __name__=="__main__":materialize()

