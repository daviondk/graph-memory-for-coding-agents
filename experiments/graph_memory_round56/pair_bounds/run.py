"""Chronological replay. Current labels enter the state only after each query."""
import argparse
from collections import Counter,defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import random
from statistics import fmean

from bounds import Neighbors,lookup

HERE=Path(__file__).resolve().parent
PAST=HERE.parents[1]/"graph_memory_round55"
MODES=("forward","reverse_miss","reverse_hit","eager","lazy")
FIELDS=("reverse","pairs","smaller_posting_visits")
CAPS=(8,16,32)

def load(p):
    raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)

def save(p,value):
    raw=(json.dumps(value,separators=(",",":"),sort_keys=True)+"\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)

def inputs():
    panels={}
    for name,p in (("A","cochange/commits.json.gz"),("B","cochange/continuation/commits.json.gz")):
        panels[name]={repo:obj["revisions"] for repo,obj in load(PAST/p).items()}
    panels["C"]={repo:[(rev,sorted(set(add)|set(drop))) for rev,add,drop in rows]
                 for repo,rows in load(PAST/"partner_clock/replication-events.json.gz").items()}
    return panels

class State:
    def __init__(self,h):
        self.h=h
        self.ids={}
        self.sketch={}
        self.recent=Counter()
        self.exposure=Counter()
        self.postings=defaultdict(set)
        self.events=[]

    def ingest(self,names,t):
        ids=[self.ids.setdefault(p,len(self.ids)) for p in names]
        assert len(set(ids))==len(ids) and len(self.events)==t
        self.events.append(tuple(ids))
        if t>=32:self.recent.subtract(self.events[t-32])
        self.recent.update(ids)
        if len(ids)<2:return
        for a in ids:
            self.exposure[a]+=1
            self.postings[a].add(t)
            sk=self.sketch.get(a)
            if sk is None:sk=self.sketch[a]=Neighbors(self.h)
            for b in ids:
                if b!=a:sk.add(b)

    def read(self,anchor):
        front=self.sketch.get(anchor)
        def forward(b):
            return front.interval(b) if front else (0,0)
        def reverse(b):
            back=self.sketch.get(b)
            return (*back.interval(anchor),anchor in back.data) if back else (0,0,False)
        def exact(b):
            return len(self.postings.get(anchor,set()) & self.postings.get(b,set()))
        pool=[i for i in range(len(self.ids)) if i!=anchor]
        gold=Counter()
        positions=0
        for t in self.postings.get(anchor,()):
            gold.update(self.events[t])
            positions+=len(self.events[t])
        expected=sorted(pool,key=lambda i:(-gold[i],-self.recent[i],i))[:8]
        packet=[(i,gold[i]) for i in expected]
        results={}
        for mode in MODES:
            pred,counts=lookup(anchor,pool,self.recent,forward,reverse,self.exposure,exact,mode)
            assert pred==packet,(mode,pred,packet)
            results[mode]=[counts[f] for f in FIELDS]
        assert results["lazy"][1:]==results["eager"][1:]
        assert results["lazy"][0]<=results["eager"][0]
        return packet,results,positions

def replay(repo,rows,h):
    mem=State(h);out=[]
    for t,(sha,names) in enumerate(rows):
        paths=names if len(names)<=64 else []
        if t>=64 and len(paths)>=2:
            name=paths[int(sha,16)%len(paths)]
            a=mem.ids.get(name,-1)
            packet,cost,positions=mem.read(a)
            targets={mem.ids.get(p,-1) for p in paths if p!=name}
            out.append(dict(t=t,sha=sha,a=a,packet=packet,cost=cost,all_positions=positions,
                            anchor_events=mem.exposure[a],pool=len(mem.ids)-int(a!=-1),
                            hits=sum(i in targets for i,v in packet),denom=len(paths)-1))
        mem.ingest(paths,t)
    return out

def aggregate(rs):
    n=len(rs)
    methods={}
    for m in MODES:
        vals=[r["cost"][m] for r in rs]
        methods[m]={f:sum(v[i] for v in vals) for i,f in enumerate(FIELDS)}
        methods[m]["fully_resolved"]=sum(v[1]==0 for v in vals)
    return dict(n=n,methods=methods,recall=fmean(r["hits"]/r["denom"] for r in rs),
                full_positions=sum(r["all_positions"] for r in rs),full_incident=sum(r["anchor_events"] for r in rs))

def summarize(groups):
    active={p:rs for p,rs in groups.items() if rs}
    grouped={p:aggregate(rs) for p,rs in active.items()}
    pooled=aggregate([r for rs in active.values() for r in rs])
    points=[(v["n"],v["methods"]["forward"]["pairs"]-v["methods"]["lazy"]["pairs"]) for v in grouped.values()]
    rng=random.Random(56015);draws=[]
    for _ in range(20000):
        sample=rng.choices(points,k=len(points))
        draws.append(sum(d for n,d in sample)/sum(n for n,d in sample))
    draws.sort()
    return dict(projects=grouped,unused=sorted(set(groups)-set(active)),pooled=pooled,
                contrast=dict(fewer_per_query=sum(d for n,d in points)/pooled["n"],
                              interval=[draws[499],draws[19499]],equal_project=fmean(d/n for n,d in points)))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    summary={}
    for h in CAPS:
        for panel,projects in inputs().items():
            groups={repo:replay(repo,rows,h) for repo,rows in projects.items()}
            key=panel+str(h)
            dest=HERE/(key+"-queries.json.gz")
            s=summarize(groups)
            if args.verify:assert load(dest)==json.loads(json.dumps(groups))
            else:save(dest,groups)
            summary[key]=s
            x=s["pooled"]; print(key,x["n"],x["methods"]["forward"],x["methods"]["lazy"],s["contrast"],flush=True)
    if args.verify:assert load(HERE/"results.json")==summary
    else:save(HERE/"results.json",summary)
if __name__=="__main__":
    main()
