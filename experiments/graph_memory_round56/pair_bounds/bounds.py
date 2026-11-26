"""Exact top-k lookup with bounded per-file Space-Saving summaries."""
from collections import Counter
from heapq import heapify, heappop, heappush, nlargest

class Neighbors:
    def __init__(self, capacity):
        self.cap = capacity
        self.data = {}
        self.overflow = False
        self.evicted_upper = 0

    def add(self, target):
        if target in self.data:
            upper,error = self.data[target]
            self.data[target] = (upper+1,error)
        elif len(self.data)<self.cap:
            self.data[target] = (1,0)
        else:
            victim = min(self.data,key=lambda i:(self.data[i][0],-i))
            upper,_ = self.data.pop(victim)
            self.evicted_upper = max(self.evicted_upper,upper)
            self.overflow = True
            self.data[target] = (upper+1,upper)

    def interval(self,target):
        state=self.data.get(target)
        if state is None:
            return 0,self.evicted_upper
        upper,error=state
        return upper-error,upper

class Floor:
    """Top k lower keys, maintained through pointwise increases."""
    def __init__(self, lower, tie, k):
        self.tie=tie
        self.best=nlargest(k,((v,tie[i],-i) for i,v in lower.items()))
        self.members={-key[2] for key in self.best}

    def update(self,i,v):
        key=(v,self.tie[i],-i)
        if key<=self.best[-1]:
            return
        if i in self.members:
            self.best=[old for old in self.best if -old[2]!=i]
        else:
            self.members.remove(-self.best.pop()[2])
            self.members.add(i)
        self.best.append(key)
        self.best.sort(reverse=True)

def lookup(anchor,pool,tie,forward,reverse,exposures,exact,mode,k=8):
    """Callbacks may read an in-memory synopsis or a relational index. Return IDs and counts."""
    stats=Counter(candidates=len(pool))
    if not pool:
        return [],stats
    lower,upper={},{}
    early=mode in {"eager","reverse_hit","reverse_miss"}
    for i in pool:
        lo,hi=forward(i)
        hi=min(hi,exposures.get(anchor,0),exposures.get(i,0))
        if early and lo<hi:
            rlo,rhi,has=reverse(i)
            stats["reverse"]+=1
            if mode=="eager" or (mode=="reverse_hit" and has) or (mode=="reverse_miss" and not has):
                lo,hi=max(lo,rlo),min(hi,rhi)
        assert 0<=lo<=hi
        lower[i],upper[i]=lo,hi
    floor=Floor(lower,tie,k)
    todo=[(-upper[i],-tie[i],i,0) for i in pool if upper[i]>lower[i] and
          (upper[i],tie[i],-i)>=floor.best[-1]]
    heapify(todo)
    while todo:
        neg_hi,neg_tie,i,stage=heappop(todo)
        if (-neg_hi,-neg_tie,-i)<floor.best[-1]:
            break
        if mode=="lazy" and stage==0:
            lo,hi,_=reverse(i)
            stats["reverse"]+=1
            lower[i],upper[i]=max(lower[i],lo),min(upper[i],hi)
            assert lower[i]<=upper[i]
            floor.update(i,lower[i])
            if lower[i]<upper[i]:
                heappush(todo,(-upper[i],neg_tie,i,1))
            continue
        val=exact(i)
        assert lower[i]<=val<=upper[i]
        stats["pairs"]+=1
        stats["smaller_posting_visits"]+=min(exposures.get(i,0),exposures.get(anchor,0))
        lower[i]=upper[i]=val
        floor.update(i,val)
    output=[(-neg_id,n) for n,_,neg_id in floor.best]
    assert all(lower[i]==upper[i] for i,_ in output)
    return output,stats
