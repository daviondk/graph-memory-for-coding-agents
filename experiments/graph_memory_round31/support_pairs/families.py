"""Exact bounded-failure caches for ranked evidence pairs."""
from functools import lru_cache
from itertools import combinations

def decision_family(edges,limit):
    """Every visited winner is realizable. Branch on a document it requires."""
    seen=set();winners=set();probes=0
    def visit(banned):
        nonlocal probes
        if banned in seen:return
        seen.add(banned)
        for rank,(a,b) in enumerate(edges):
            probes+=1
            if a in banned or b in banned:continue
            winners.add(rank)
            if len(banned)<limit:
                visit(banned|{a});visit(banned|{b})
            break
    visit(frozenset())
    return sorted(winners),probes

PRIME=101
@lru_cache(None)
def wedge(a,b,degree):
    x=[pow(a+1,i,PRIME) for i in range(degree)]
    y=[pow(b+1,i,PRIME) for i in range(degree)]
    return tuple((x[i]*y[j]-x[j]*y[i])%PRIME for i,j in combinations(range(degree),2))

def linear_family(edges,n,limit):
    """Greedy minimum-rank basis of exterior products of document columns."""
    degree=min(n,2+limit);dimension=degree*(degree-1)//2
    basis={};ranks=[]
    for idx,(a,b) in enumerate(edges):
        v=list(wedge(a,b,degree))
        for pivot in range(dimension):
            c=v[pivot]
            if not c:continue
            if pivot not in basis:
                inv=pow(c,-1,PRIME)
                basis[pivot]=[(x*inv)%PRIME for x in v];ranks.append(idx);break
            other=basis[pivot]
            for k in range(pivot,dimension):v[k]=(v[k]-c*other[k])%PRIME
        if len(basis)==dimension:break
    return ranks

@lru_cache(None)
def failures(n):
    return [(k,sum(1<<i for i in nodes)) for k in range(4) for nodes in combinations(range(n),k)]

