"""Exhaust all ranked triples of monotone availability functions on three sources."""
from itertools import product
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def subset(left,right):return left & right==left
def families(n):
    sets=range(1<<n)
    for mask in range(1<<len(sets)):
        witnesses=tuple(s for s in sets if mask>>s&1)
        if all(a==b or not subset(a,b) for a in witnesses for b in witnesses):yield witnesses
def possible(candidates):
    higher=[];kept=[]
    for i,family in enumerate(candidates):
        if any(all(not subset(other,w) for other in higher) for w in family):kept.append(i)
        higher.extend(family)
    return kept
def verify():
    fs=list(families(3));assert len(fs)==20
    triples=states=checks=extra=0
    for candidates in product(fs,repeat=3):
        kept=possible(candidates);seen=set();triples+=1
        for state in range(8):
            allowed=[i for i,family in enumerate(candidates) if any(subset(w,state) for w in family)]
            winner=allowed[0] if allowed else None
            if winner is not None:seen.add(winner)
            assert next((i for i in kept if i in allowed),None)==winner;states+=1
            for k in range(1,4):
                ordinary=winner is not None and winner<k
                filtered=winner is not None and winner in kept[:k]
                assert not ordinary or filtered
                checks+=1;extra+=int(filtered and not ordinary)
        assert sorted(seen)==kept
    assert possible([(1,),(2,),(1,2)])==[0,1]
    return {"sources":3,"candidate_ids":3,"families":len(fs),"ranked_triples":triples,"state_cases":states,
            "cache_checks":checks,"filtered_only_hits":extra}
if __name__=="__main__":
    (HERE/"results.json").write_text(json.dumps(verify(),sort_keys=True,indent=2)+"\n",encoding="utf8")
