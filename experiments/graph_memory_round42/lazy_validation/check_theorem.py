"""Check the certificate against every possible completion, including ties and zero costs."""
from itertools import combinations
import json
from pathlib import Path
from random import Random
from lazy import first_risk

def subsets(ids):
    for size in range(len(ids)+1):
        yield from combinations(ids,size)

def optimum(rows, threshold, capacity):
    head=[];used=0
    for i,_,cost,_ in rows:
        if used+cost>threshold:
            break
        head.append(i);used+=cost
    tail=rows[len(head):]
    best=(0,0);ids=()
    for s in subsets(tail):
        if sum(x[2] for x in s)+used>capacity:
            continue
        score=(sum(x[3] for x in s),-sum(1<<x[0] for x in s))
        if score>best:
            best=score;ids=tuple(x[0] for x in s)
    return head+list(ids)

def main():
    rng=Random(421174);n_keys=n_completions=approved=0
    for pool in range(180):
        rows=[(i,0,rng.randrange(6),rng.randrange(4)) for i in range(3+pool%5)]
        T=rng.randrange(10);B=T+rng.randrange(9)
        baseline=optimum(rows,T,B)
        ids=[x[0] for x in rows];answers={}
        for remove in subsets(ids):
            gone=set(remove)
            answers[frozenset(gone)]=optimum([r for r in rows if r[0] not in gone],T,B)
        for uncertain in subsets(ids):
            unknown=set(uncertain);n_keys+=1
            predicted=not(set(baseline)&unknown) and first_risk(rows,set(baseline),unknown,T) is None
            possible=[answers[frozenset(x)]==baseline for x in subsets(uncertain)]
            n_completions+=len(possible);approved+=predicted
            assert predicted==all(possible)
    out=dict(pools=180,uncertain_configurations=n_keys,completion_comparisons=n_completions,certified=approved,errors=0)
    Path(__file__).with_name("theorem-check.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf8")
    print(out)

if __name__=="__main__":
    main()
