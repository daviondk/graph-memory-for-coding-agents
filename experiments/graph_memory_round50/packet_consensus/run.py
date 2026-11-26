"""Freeze retrieval predictions for five-model ensembles before loading relevance."""
import ctypes as ct
import gzip
from pathlib import Path
import sys
import numpy as np

D = Path(__file__).resolve().parent
BASE = D.parent/"matched_reader"
sys.path.insert(0,str(BASE))
from common import SEEDS,sha,read,put
from runtime import Reader
from run_matched import select

PROTOCOL = "aba32a48f123679594869dc9ed500964af43ebfa282f8db42ea56fad5721ae7e"


def signed(name):
    p = BASE/name
    assert sha(p)==read(BASE/"manifest.json")["files"][name]
    return p


def main():
    assert sha(D/"PROTOCOL_RU.md")==PROTOCOL
    pool=read(signed("pool.json.gz"))
    ranks=[read(signed(f"ranks-{s}.json.gz")) for s in SEEDS]
    prior=[read(signed(f"archive-{s}.json.gz")) for s in SEEDS]
    gains=[np.frombuffer(gzip.decompress(signed(f"utility-{s}.f64.gz").read_bytes()),dtype="<f8") for s in SEEDS]
    reader=Reader(False)
    fn=reader.lib.packet
    fn.argtypes=[ct.c_int]*3+[ct.c_void_p]*4
    fn.restype=ct.c_int
    batches={}
    offset=0
    for q,r in sorted(pool.items()):
        cost=np.asarray(r["c"],dtype=np.int32)
        n=len(cost)
        mean=np.mean([u[offset:offset+n] for u in gains],axis=0)
        offset+=n
        checkpoints=[]
        for cp in (0,1):
            denom=np.zeros(n)
            ballots=[]
            teacher=[]
            for rank,forecast in zip(ranks,prior):
                order=np.asarray(rank[q][1+cp])
                denom[order]+=1/(60+np.arange(1,n+1))
                ids=forecast[q][cp][0]
                teacher.append(ids)
                ballots.append(set(ids))
            # Stable candidate ID resolves exact reciprocal-rank ties.
            order=np.argsort(-denom,kind="stable").astype(np.int32)
            cfg={"costs":cost,"order":order}
            votes=np.zeros(n)
            for ids in teacher:votes[ids]+=1
            mid=min(range(len(ballots)),key=lambda i:sum(len(ballots[i]^a) for a in ballots))
            pooled={
                "native_rrf":select(fn,3,0,cfg,None),
                "mean_dp":select(fn,0,0,cfg,mean),
                "mean_greedy":select(fn,4,0,cfg,mean),
                "votes_dp":select(fn,0,0,cfg,votes),
                "votes_greedy":select(fn,4,0,cfg,votes),
                "hamming_dp":select(fn,0,0,cfg,2*votes-5),
                "medoid":teacher[mid]
            }
            for j,ids in enumerate(teacher):
                pooled[f"single_{SEEDS[j]}"]=ids
            assert all(len(x)==len(set(x)) and sum(cost[x])<=2048 for x in pooled.values())
            checkpoints.append(pooled)
        batches[q]=[r["t"],checkpoints]
    assert all(offset==len(g) for g in gains)
    put(D/"packets.json.gz",batches)
    put(D/"forecast-seal.json",dict(code=sha(Path(__file__)), protocol=PROTOCOL,matched=sha(BASE/"manifest.json"),
        forecasts=sha(D/"packets.json.gz"),n=len(batches)))

if __name__=="__main__":
    main()

