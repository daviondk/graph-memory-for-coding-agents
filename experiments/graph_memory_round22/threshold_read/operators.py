"""Exact token-budgeted retrieval from a semantic rank stream plus cached graph priors."""
from dataclasses import dataclass
import heapq
import numpy as np


@dataclass
class Index:
    prior: np.ndarray
    costs: np.ndarray
    by_prior: np.ndarray
    sorted_priors: np.ndarray
    by_cost: np.ndarray
    sorted_costs: np.ndarray


def index(prior, costs):
    p=np.asarray(prior,dtype=np.float64);c=np.asarray(costs,dtype=np.int64)
    assert p.shape==c.shape and p.ndim==1 and (c>0).all() and np.isfinite(p).all()
    high=np.argsort(-p,kind="stable");small=np.argsort(c,kind="stable")
    return Index(p,c,high,p[high],small,c[small])


def suffix_bounds(rank_scores):
    signal=np.asarray(rank_scores,dtype=np.float64)
    assert signal.ndim==1 and np.isfinite(signal).all()
    return np.maximum.accumulate(signal[::-1])[::-1]


def counters():
    return {k:0 for k in ("scored","dense_cursor","prior_cursor","rank_index_build","rank_random","prior_random",
                           "cost_random","cost_cursor","heap_pops","bound_probes")}


def pack(nodes,costs,budget,policy,m):
    keep=[];left=budget
    for unit in nodes:
        if left==0:break
        m["cost_random"]+=1
        price=int(costs[unit])
        if price<=left:
            keep.append(int(unit));left-=price
            if left==0:break
        elif policy=="prefix":break
    return keep


def score_all(order,signal,upper,idx,budget,policy,method):
    n=len(order);m=counters()
    m.update(scored=n,prior_random=n,dense_cursor=n)
    absolute=signal+idx.prior[order]
    if method=="vector":
        pos=np.argsort(-absolute,kind="stable")
        nodes=(order[j] for j in pos)
    else:
        hp=[(-float(s),j) for j,s in enumerate(absolute)]
        heapq.heapify(hp)
        def top():
            while hp:
                _,j=heapq.heappop(hp);m["heap_pops"]+=1
                yield order[j]
        nodes=top()
    return pack(nodes,idx.costs,budget,policy,m),m


def threshold(order,signal,upper,idx,budget,policy,method):
    two=method=="two";n=len(order);m=counters()
    if not n or not budget:return [],m
    inv=None
    if two:
        inv=np.empty(n,dtype=np.int64);inv[order]=np.arange(n)
        m["rank_index_build"]=n
    seen=bytearray(n);popped=bytearray(n)
    prior_pos=cost_pos=rank_pos=0
    heap=[];kept=[];left=budget

    def add(node,position):
        if seen[node]:return
        seen[node]=1;m["scored"]+=1;m["prior_random"]+=1
        heapq.heappush(heap,(-float(signal[position]+idx.prior[node]),position,node))

    while rank_pos<n:
        node=int(order[rank_pos]);add(node,rank_pos);rank_pos+=1;m["dense_cursor"]=rank_pos
        if two:
            while prior_pos<n and seen[idx.by_prior[prior_pos]]:prior_pos+=1
            if prior_pos<n:
                node=int(idx.by_prior[prior_pos]);m["rank_random"]+=1
                add(node,int(inv[node]));prior_pos+=1
        while prior_pos<n and seen[idx.by_prior[prior_pos]]:prior_pos+=1
        m["prior_cursor"]=min(n,prior_pos+1)
        if rank_pos==n or prior_pos==n:
            bound=-float("inf")
        else:
            bound=float(upper[rank_pos]+idx.sorted_priors[prior_pos]);m["bound_probes"]+=1
        # Equality cannot certify a result until semantic-rank tie order is known.
        while heap and -heap[0][0]>bound:
            _,_,node=heapq.heappop(heap);m["heap_pops"]+=1;popped[node]=1
            cost=int(idx.costs[node]);m["cost_random"]+=1
            if cost<=left:
                kept.append(node);left-=cost
                if not left:return kept,m
            elif policy=="prefix":return kept,m
            if policy=="skip":
                while cost_pos<n and popped[idx.by_cost[cost_pos]]:cost_pos+=1
                m["cost_cursor"]=min(n,cost_pos+1)
                if cost_pos==n or idx.sorted_costs[cost_pos]>left:return kept,m
        if prior_pos==n:return kept,m
    return kept,m


def read(method,order,signal,upper,idx,budget,policy):
    if method in ("vector","heap"):
        return score_all(order,signal,upper,idx,budget,policy,method)
    return threshold(order,signal,upper,idx,budget,policy,method)

