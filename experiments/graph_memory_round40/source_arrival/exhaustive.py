"""Compare stable integer packing and arbitrary arrivals with literal subset enumeration."""
from itertools import combinations
import random
import numpy as np
from experiment import Planner, save


def oracle(ids,cost,gain,budget):
    head=[]
    used=0
    for i in ids:
        if used+cost[i] > budget//2:
            break
        head.append(i)
        used+=cost[i]
    tail=list(ids[len(head):])
    winner=(0,0)
    for bits in range(1<<len(tail)):
        subset=[i for j,i in enumerate(tail) if bits>>j&1]
        if used+sum(cost[i] for i in subset) <= budget:
            score=(sum(gain[i] for i in subset),-sum(1<<i for i in subset))
            winner=max(winner,score)
    return tuple(head+[i for i in tail if (-winner[1])>>i&1])


def main():
    rng=random.Random(405301)
    cases=certified=ties=0
    for _ in range(180):
        n=rng.randint(3,8)
        cost=[rng.randint(1,11) for _ in range(n)]
        gain=[rng.randint(0,4) for _ in range(n)]
        budget=rng.randint(1,23)
        planner=Planner(cost,gain,budget)
        all_ids=list(range(n))
        for _ in range(12):
            oldids=np.array(sorted(rng.sample(all_ids,rng.randrange(n))),dtype=np.int32)
            free=sorted(set(all_ids)-set(oldids))
            old=planner.full(oldids)
            assert old[0]==oracle(oldids.tolist(),cost,gain,budget)
            for size in range(1,min(3,len(free))+1):
                for subset in combinations(free,size):
                    new=np.array(sorted(set(subset)|set(oldids)),dtype=np.int32)
                    target=oracle(new.tolist(),cost,gain,budget)
                    result,mode=planner.update(old,new,np.asarray(subset,dtype=np.int32))
                    assert result==target==planner.full(new)[0]
                    cases+=1
                    certified+=mode=="strict_certificate"
                    ties+=mode=="tie"
    # Head has one unit of size 10. In C=10 an incumbent (cost 8, utility 10)
    # defeats either incoming item (5,6) but loses to the pair.
    plan=Planner([10,8,5,5],[1,10,6,6],20)
    old=plan.full(np.array([0,1],dtype=np.int32))
    one=[plan.update(old,np.array([0,1,i],np.int32),np.array([i],np.int32))[1] for i in (2,3)]
    both=plan.update(old,np.arange(4,dtype=np.int32),np.array([2,3],np.int32))
    assert one==["strict_certificate"]*2 and both==((0,2,3),"better_tail")
    result=dict(checked=cases,positive=certified,tie_fallback=ties,synergy=both[0])
    save("exhaustive.json",result)
    print(result)


if __name__=="__main__":
    main()

