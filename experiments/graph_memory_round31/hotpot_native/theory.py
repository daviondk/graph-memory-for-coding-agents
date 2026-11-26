"""Independent exhaustive and stochastic checks of the post-hoc exchange lemma."""
from itertools import combinations, permutations
from functools import lru_cache
from random import Random
from collections import Counter
from pathlib import Path
import json
import time
from run import HERE, sha, put

def case(n, beam, depth, order):
    pairs=[sum(1<<j for j in edge) for edge in order]
    full_mask=(1<<n)-1
    @lru_cache(None)
    def optimum(ban):
        live=full_mask^ban; pool=0; bits=live
        for _ in range(beam):
            if not bits:break
            bit=bits&-bits;pool|=bit;bits^=bit
        return next((i for i,v in enumerate(pairs) if not v&ban and v&pool),None)
    masks=[sum(1<<j for j in x) for k in range(depth+1) for x in combinations(range(n),k)]
    truths={optimum(r) for r in masks}
    assert None not in truths
    visited=set();found=set()
    def recur(r):
        if r in visited:return
        visited.add(r); w=optimum(r);found.add(w)
        if r.bit_count()==depth:return
        vals=pairs[w]
        while vals:
            x=vals&-vals;recur(r|x);vals^=x
    recur(0)
    assert truths==found and len(visited)<=2**(depth+1)-1
    roots=list(range(min(beam+depth,n)))
    for ban in masks:
        first=[i for i in roots if not ((1<<i)&ban)][:beam];gate=sum(1<<i for i in first)
        returned=next((i for i in sorted(found) if not pairs[i]&ban and pairs[i]&gate),None)
        assert returned==optimum(ban)
    base=optimum(0)
    indirect=sum(int(not(pairs[base]&r) and optimum(r)!=base) for r in masks)
    return len(masks),len(visited),len(found),indirect

def main():
    rng=Random(318721); stats=Counter(); maxima=Counter();hist=Counter();start=time.monotonic()
    def update(mode, k, result):
        nm,vis,rows,indir=result
        stats[mode+"_graphs"]+=1;stats[mode+"_states"]+=nm;stats[mode+"_changed_surviving_states"]+=indir
        maxima[str(k)]=max(maxima[str(k)],rows);hist[(k,vis,rows)]+=1
    for order in permutations(combinations(range(4),2)):
        for b in (1,2,3):
            for k in (1,2):
                update("exhaustive_n4",k,case(4,b,k,order))
    for _ in range(12000):
        n=rng.randint(5,12);k=rng.randint(1,min(3,n-2));b=rng.randint(1,min(5,n-k))
        edges=list(combinations(range(n),2));rng.shuffle(edges)
        update("random",k,case(n,b,k,edges))
    put(HERE/"theory-check.json",{"stats":stats,"max_stored_by_depth":maxima,"hist":[[*k,num] for k,num in sorted(hist.items())],"code":sha(Path(__file__)),"lemma":sha(HERE/"EXCHANGE_RU.md"),"seconds":time.monotonic()-start})
    print(stats, maxima)
if __name__=="__main__":main()
