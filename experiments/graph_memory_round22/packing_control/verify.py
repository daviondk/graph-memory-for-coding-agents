"""Replay strict evidence and the cluster bootstrap from the portable archives."""
from collections import defaultdict
from pathlib import Path
import gzip
import hashlib
import json
import sys
import numpy as np

D=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def union(seq):
    out=[]
    for l,h in sorted(seq):
        if out and l<=out[-1][1]:out[-1][1]=max(out[-1][1],h)
        else:out.append([l,h])
    return out
def nums(spans):
    groups=defaultdict(list)
    for eid,ptr,l,h in spans:groups[eid,ptr].append((l,h))
    return {k:union(v) for k,v in groups.items()}
def main():
    off=D.parents[1]/"graph_memory_round18/isetrace_official"
    src=read(off/"gold-spans.json.gz");truth={q:nums([(s["event_id"],s["json_pointer"],s["char_start"],s["char_end"]) for s in spans]) for q,spans in src.items()}
    metrics=read(D/"strict-metrics.json.gz");rep=read(D/"results.json");renders=read(D/"no-next-render-seal.json")["files"]
    assert rep["strict_outcomes"]==sha(D/"strict-metrics.json.gz")
    count=0
    for name,h in renders.items():
        assert sha(D/name)==h
        for r in read(D/name):
            q=r["q"];ad=r["addr"];g=truth[q];ng=sum(h-l for v in g.values() for l,h in v)
            for a,(nominal,real,paid,parts) in r["picks"].items():
                part=nums([(*ad[e],l,h) for e,l,h in parts]);den=sum(h-l for _,l,h in parts)
                overlap=sum(max(0,min(v,y)-max(u,x)) for k,arr in part.items() for u,v in arr for x,y in g.get(k,[]))
                v=metrics[a][q];assert v["t"]==r["t"] and 0<=paid<=2048 and v["tokens"]==paid
                assert abs(v["coverage"]-overlap/ng)<1e-12 and v["full_support"]==int(overlap==ng)
                assert abs(v["density"]-(overlap/den if den else 0))<1e-12;count+=1
    assert count==4000
    fields=("full_support","coverage","density","f1","tokens")
    by=defaultdict(list)
    for q in sorted(truth):
        a,b=metrics["ratio"][q],metrics["skip"][q];by[a["t"]].append([a[k]-b[k] for k in fields])
    assert len(by)==1207 and len(truth)==2000
    sz=np.array([len(by[t]) for t in sorted(by)]);ss=np.asarray([np.sum(by[t],axis=0) for t in sorted(by)])
    rng=np.random.default_rng(13);samples=[]
    for _ in range(100):
        ix=rng.integers(0,len(sz),size=(100,len(sz)));samples.append(ss[ix].sum(axis=1)/sz[ix].sum(axis=1)[:,None])
    ci=np.quantile(np.concatenate(samples),[.025,.975],axis=0)
    for j,k in enumerate(fields):
        z=rep["pairs"]["differences"][k]
        assert np.allclose(ci[:,j],z["cluster_ci95"],atol=1e-12,rtol=0)
        assert abs(ss.sum(axis=0)[j]/2000-z["estimate"])<1e-12
    print("Verified 4,000 strict source outcomes and 10,000 trajectory bootstrap samples.")
if __name__=="__main__":main()

