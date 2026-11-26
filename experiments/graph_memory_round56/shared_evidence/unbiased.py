"""Exact design expectations over all independently selected per-file reservoirs."""
from fractions import Fraction
from collections import Counter
from itertools import combinations,product
from math import prod
from retain import HERE
from run import save

def check(b):
    events=[("a","b"),("a","c"),("a","b","c"),("b","d"),("c","d"),("a","d")]
    files=sorted({f for e in events for f in e})
    incident={f:[i for i,e in enumerate(events) if f in e] for f in files}
    choices=[list(combinations(v,min(b,len(v)))) for v in incident.values()]
    inclusion=[1-prod(1-Fraction(min(b,len(incident[f])),len(incident[f])) for f in e) for e in events]
    hits=Counter()
    states=0
    for joint in product(*choices):
        states+=1
        hits.update(set(x for owner in joint for x in owner))
    assert [Fraction(hits[i],states) for i in range(len(events))]==inclusion
    pairs=list(combinations(files,2))
    for a,y in pairs:
        expectation=sum(Fraction(hits[i],states)/inclusion[i] for i,e in enumerate(events) if a in e and y in e)
        assert expectation==sum(a in e and y in e for e in events)
    return dict(budget=b,weight_checks=len(pairs),states=states,inclusion=[str(p) for p in inclusion])

if __name__=="__main__":
    out=[check(b) for b in (1,2,3)]
    save(HERE/"design-check.json",out)
    print(out)
