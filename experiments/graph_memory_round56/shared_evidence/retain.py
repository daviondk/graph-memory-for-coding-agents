"""Shared physical events, per-owner retention, and exact bounds for the evicted complement."""
from collections import Counter,defaultdict
from hashlib import blake2b
from heapq import nlargest
from math import prod
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"pair_bounds"))
from bounds import lookup

class Retained:
    def __init__(self,cap,policy,repo):
        self.cap,self.policy,self.repo=cap,policy,repo
        self.owned={}
        self.owners=Counter()
        self.events={}
        self.incident=defaultdict(set)
        self.total=Counter()
        self.emitted=0

    def drop_owner(self,t):
        self.owners[t]-=1
        if self.owners[t]:return
        del self.owners[t]
        for f in self.events.pop(t):
            self.incident[f].remove(t)

    def ingest(self,ids,names,sha,t):
        if len(ids)<2:return
        self.emitted+=1
        self.total.update(ids)
        for f,name in zip(ids,names):
            own=self.owned.setdefault(f,[])
            value=t
            if self.policy=="hash":
                content=("\0".join(("56027",self.repo,name,sha))).encode("utf8","surrogateescape")
                value=-int.from_bytes(blake2b(content,digest_size=12).digest(),"big")
            if len(own)==self.cap and (value,t)<=own[0]:
                continue
            if len(own)==self.cap:
                _,old=own.pop(0)
                self.drop_owner(old)
            own.append((value,t))
            own.sort()
            if not self.owners[t]:
                self.events[t]=tuple(ids)
                for b in ids:self.incident[b].add(t)
            self.owners[t]+=1

    def score(self,ids,weights=None):
        freq=Counter()
        for t in ids:
            if weights is None:
                freq.update(self.events[t])
            else:
                for i in self.events[t]:freq[i]+=weights[t]
        return freq

    def read(self,a,pool,tie,truth):
        own=[t for priority,t in self.owned.get(a,())]
        seen=sorted(self.incident.get(a,()))
        small=sorted(seen,key=lambda t:(len(self.events[t]),-t))[:self.cap]
        lost_a=self.total[a]-len(seen)
        lost_total=self.emitted-len(self.events)
        groups={"own":own,"shared":seen,"small":small}
        weights={}
        if self.policy=="hash":
            groups["weighted"]=seen
            for t in seen:
                pi=1-prod(1-min(1.,self.cap/self.total[i]) for i in self.events[t])
                weights[t]=1/pi
        packets={};cost={}
        shared=self.score(seen)
        for mode,js in groups.items():
            scores=shared if mode=="shared" else self.score(js,weights if mode=="weighted" else None)
            ranks=nlargest(8,pool,key=lambda i:(scores[i],tie[i],-i))
            packets[mode]=[(i,scores[i]) for i in ranks]
            cost[mode]=[len(js),sum(len(self.events[t]) for t in js)]
        def interval(b):
            lost_b=self.total[b]-len(self.incident.get(b,()))
            return shared[b]+max(0,lost_a+lost_b-lost_total),shared[b]+min(lost_a,lost_b)
        exact,stats=lookup(a,pool,tie,interval,None,self.total,lambda b:truth[b],"forward")
        return packets,cost,exact,stats["pairs"],lost_a
