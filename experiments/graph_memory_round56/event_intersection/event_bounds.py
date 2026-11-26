"""Sharp bounds from two truncated chronological event lists and their cardinalities."""
from bisect import bisect_left
from collections import Counter
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"pair_bounds"))
from bounds import lookup

def common(a,b):
    # For strict suffixes, every timestamp shared by the two retained lists is
    # automatically in their common fully observed region.
    return len(set(a).intersection(b))

def bounds(a,b,na,nb,rule="aligned"):
    if not na or not nb:return 0,0,0,0
    ta=a[0] if na>len(a) else 0
    tb=b[0] if nb>len(b) else 0
    c=max(ta,tb)
    z=common(a,b)
    if rule=="counts":return 0,min(na,nb),0,0
    if rule=="unaligned":
        # A missing true intersection uses at least one omitted posting.
        return z,min(na,nb,z+na-len(a)+nb-len(b)),0,0
    ra=na-len(a)+bisect_left(a,c)
    rb=nb-len(b)+bisect_left(b,c)
    return z+max(0,ra+rb-c),z+min(ra,rb),c,z

class EpisodeState:
    def __init__(self,budget):
        self.budget=budget
        self.recent={}
        self.count=Counter()
        self.all={}
        self.members=[]
        self.bitset={}
        self.writes=0

    def observe(self,ids):
        if len(ids)<2:return
        j=len(self.members)
        self.members.append(tuple(ids))
        bit=1<<j
        for i in ids:
            self.recent[i]=(self.recent.get(i,())+(j,))[-self.budget:]
            self.count[i]+=1
            self.all.setdefault(i,[]).append(j)
            self.bitset[i]=self.bitset.get(i,0)|bit
            self.writes+=1

    def packet(self,a,pool,freq,rule,sql=None):
        work=Counter()
        cutoffs={}
        na=self.count[a]
        sa=self.recent.get(a,())
        def forward(i):
            lo,hi,c,z=bounds(sa,self.recent.get(i,()),na,self.count[i],rule)
            if lo<hi:cutoffs[i]=(c,z)
            return lo,hi
        def exact(i):
            c,z=cutoffs[i]
            if rule=="aligned":
                sb=self.recent.get(i,())
                pa=na-len(sa)+bisect_left(sa,c)
                pb=self.count[i]-len(sb)+bisect_left(sb,c)
            else:
                pa,pb=na,self.count[i]
                z=0
                c=len(self.members)
            work["prefix_probes"]+=min(pa,pb)
            if sql:
                return z+sql(a,i,c,pa<=pb)
            olda=self.all.get(a,())
            oldb=self.all.get(i,())
            return z+len(set(olda[:pa]).intersection(oldb[:pb]))
        ranks,stats=lookup(a,pool,freq,forward,None,self.count,exact,"forward")
        return ranks,dict(pairs=stats["pairs"],prefix=work["prefix_probes"])
