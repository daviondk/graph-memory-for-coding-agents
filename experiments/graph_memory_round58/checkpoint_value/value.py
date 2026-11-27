"""Exact additive source savings and all-or-nothing posting-list savings."""
from collections import Counter
from itertools import combinations
import numpy as np


def gain(chosen, values, bonuses):
    return (sum(values.get(j,0) for j in chosen),
            sum(reward for required,reward in bonuses.items() if required<=chosen))


def knapsack(cost, rewards, capacity):
    items=[j for j in sorted(cost) if rewards.get(j,0)>0 and cost[j]<=capacity]
    dp=np.zeros(capacity+1,dtype=np.int64)
    decisions=[]
    for j in items:
        w=cost[j]
        take=dp[:-w]+rewards[j]
        improve=take>dp[w:]
        dp[w:]=np.maximum(dp[w:],take)
        decisions.append(improve)
    cap=capacity
    path=set()
    for j,improve in zip(reversed(items),reversed(decisions)):
        w=cost[j]
        if cap>=w and improve[cap-w]:
            path.add(j)
            cap-=w
    assert sum(rewards[j] for j in path)==dp[capacity] and sum(cost[j] for j in path)<=capacity
    return int(dp[capacity]),path


def bracket(cost, values, bonuses, capacity, controls=()):
    lower=0
    upper=None
    best=set()
    choices=list(controls)
    for kind in ("body","even","first","last"):
        surrogate=Counter(values)
        if kind!="body":
            for required,reward in bonuses.items():
                group=sorted(required)
                if kind=="even":
                    div,rem=divmod(reward,len(group))
                    surrogate.update({j:div+(p<rem) for p,j in enumerate(group)})
                else:
                    surrogate[group[-1] if kind=="last" else group[0]]+=reward
        linear,subset=knapsack(cost,surrogate,capacity)
        choices.append(subset)
        if kind!="body":
            upper=linear if upper is None else min(upper,linear)
    for subset in choices:
        assert sum(cost[j] for j in subset)<=capacity
        realized=sum(gain(subset,values,bonuses))
        if realized>lower:
            best=set(subset)
            lower=realized
    assert upper>=lower
    return lower,upper,sorted(best)


def tiny():
    from random import Random
    rng=Random(58190)
    cases=exact=convex=0
    for n in range(1,8):
        ids=range(n)
        subsets=[frozenset(s) for k in range(n+1) for s in combinations(ids,k)]
        for _ in range(20):
            cost={i:rng.randint(1,6) for i in ids}
            values={i:rng.randint(0,10) for i in ids}
            bonuses={s:rng.randrange(20) for s in subsets if s and rng.random()<.14}
            cap=rng.randint(0,sum(cost.values()))
            feasible=[s for s in subsets if sum(cost[j] for j in s)<=cap]
            highest=max(sum(gain(s,values,bonuses)) for s in feasible)
            lo,hi,_=bracket(cost,values,bonuses,cap)
            assert lo<=highest<=hi
            exact+=lo==hi
            g={s:sum(gain(s,values,bonuses)) for s in subsets}
            for s in subsets:
                for i,j in combinations(set(ids)-s,2):
                    assert g[s|{i,j}]-g[s|{i}]>=g[s|{j}]-g[s]
                    convex+=1
            cases+=1
    return dict(cases=cases, closed=exact, supermodular_square_checks=convex)
