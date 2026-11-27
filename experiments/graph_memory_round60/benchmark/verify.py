"""Independent, stdlib-only replay and enumerator of the primary null."""
from collections import Counter, defaultdict
from fractions import Fraction
from math import comb
from common import HERE, load, sha

def main():
    for receipt in ("decision-seal.json","result-seal.json"):
        for filename,digest in load(HERE/receipt).items():
            assert sha(HERE/filename)==digest,filename
    inputs=load(HERE/"inputs.json.gz")
    items=load(HERE/"per_item.json.gz")
    labels=load(HERE/"labels.json.gz")
    result=load(HERE/"results.json")
    assert len(items)==len(inputs)==len(labels)==357
    sys_counts=Counter()
    groups=defaultdict(list)
    for i,(q,r,y) in enumerate(zip(inputs,items,labels,strict=True)):
        assert r["task"]==q["task"]==y["task"]
        for model,rank in q["ranks"].items():
            assert len(set(rank))==len(rank)
            assert r["hit"][model]==(rank[0] in y["positive_ids"])
        agreement=len({q["ranks"][k][0] for k in ("bm25_outcome","sparse_fields","fusion")})==1
        assert agreement==r["skip_three"]
        if i>=99: continue
        exposed=not agreement
        card,nt,ot=q["readers"]["full"]
        assert card in q["ranks"]["fusion"][:5]
        chosen=card if exposed else q["ranks"]["fusion"][0]
        assert r["score"]["full_three"]==[chosen,nt*exposed,ot*exposed]
        assert r["hit"]["full_three"]==(chosen in y["positive_ids"])
        sys_counts.update(dict(matches=int(r["hit"]["full_three"]),calls=int(exposed),input=nt*exposed,output=ot*exposed))
        advantage=int(q["ranks"]["fusion"][0] in y["positive_ids"])-int(card in y["positive_ids"])
        groups[q["repo"]].append((agreement,advantage))
    assert sys_counts=={"matches":73,"calls":31,"input":104401,"output":62}
    # Count every subset by dynamic programming per repository independently of grade.py.
    all_ways={0:1}
    for g in groups.values():
        k=sum(s for s,d in g)
        counts={(0,0):1}
        for _,d in g:
            next_counts=counts.copy()
            for (n,v),count in counts.items():
                if n<k: next_counts[n+1,v+d]=next_counts.get((n+1,v+d),0)+count
            counts=next_counts
        ways={v:c for (n,v),c in counts.items() if n==k}
        assert sum(ways.values())==comb(len(g),k)
        convolved=Counter()
        for d,c in all_ways.items():
            for e,n in ways.items(): convolved[d+e]+=c*n
        all_ways=convolved
    null=result["null"]["three"]
    av=result["lite"]["results"]["full"]["any"]
    assert {str(av+d):str(c) for d,c in all_ways.items()}==null["outcomes"]
    denom=sum(all_ways.values())
    assert float(Fraction(sum(c for d,c in all_ways.items() if av+d>=73),denom))==null["prob_hit_at_least_observed"]
    assert result["R59_graph"]["results"]["true_three"]["any"]==result["R59_graph"]["results"]["flat_three"]["any"]==45
    from itertools import combinations
    controls=load(HERE/"control-results.json")
    assert all(sha(HERE/k)==v for k,v in load(HERE/"control-seal.json").items())
    for name,parts in load(HERE/"control-schedules.json").items():
        fixed=0
        ways=Counter({0:1})
        for part in parts.values():
            gain=lambda i:int(items[i]["hit"]["full"])-int(items[i]["hit"]["fusion"])
            fixed+=sum(map(gain,part["take"]))
            ties=Counter(sum(map(gain,subset)) for subset in combinations(part["tie"],part["tie_count"]))
            merged=Counter()
            for k,n in ties.items():
                for j,m in ways.items():merged[k+j]+=n*m
            ways=merged
        assert {str(65+fixed+k):str(v) for k,v in ways.items()}==controls[name]["distribution"]
    print("Verified 357 ID rows, 99 complete matched readers and exact random-routing distribution.")

if __name__=="__main__":main()

