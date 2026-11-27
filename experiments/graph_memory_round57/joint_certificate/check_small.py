"""Enumerate actual small histories, group observationally identical packets, check soundness."""
from collections import Counter,defaultdict
from itertools import combinations,combinations_with_replacement,product

from certificate import bounds,certify,materialize,unpack,UNIT
from run import HERE,oracle,write

def main():
    a,b=0,1
    candidates=tuple(range(2,7));all_ids=list(range(2,13))
    frequency=Counter({x:x%2 for x in all_ids})
    catalog={"a":[(a,*c) for c in combinations(candidates,2)],
             "b":[(b,*c) for c in combinations(candidates,2)],
             "j":[(a,b,c) for c in candidates]}
    counts=Counter()
    for na,nb,nj in ((1,1,1),(1,1,2),(2,1,1)):
        groups=defaultdict(list)
        for ea,eb,ej in product(combinations_with_replacement(catalog["a"],na),
               combinations_with_replacement(catalog["b"],nb),combinations_with_replacement(catalog["j"],nj)):
            world=ea+eb+ej
            selected=list(range(len(world)))
            packet,_=materialize(selected,world,a,b)
            gold=oracle(selected,world,a,b,all_ids,frequency)
            predicted,stat=certify(packet,frequency,all_ids,world.__getitem__)
            assert predicted==gold
            groups[packet].append((tuple(gold),Counter(x for e in ej for x in e if x not in (a,b)),stat))
            counts["worlds"]+=1
        for raw,variants in groups.items():
            counts["summary_groups"]+=1
            s=unpack(raw)[3]
            limits=bounds(3,s,True)
            for _,true,_ in variants:
                assert all(lo<=true[x]*UNIT<=hi for x,(lo,hi) in limits.items())
            ranks={tuple(x for x,_ in gold) for gold,_,_ in variants}
            answers={gold for gold,_,_ in variants}
            cert=variants[0][2]
            assert all(stat["initial_ids"]==cert["initial_ids"] and stat["initial_scores"]==cert["initial_scores"]
                       for _,_,stat in variants)
            assert not cert["initial_ids"] or len(ranks)==1
            assert not cert["initial_scores"] or len(answers)==1
            counts["ambiguous_answer_groups"]+=len(answers)>1
            counts["ambiguous_order_groups"]+=len(ranks)>1
            counts["certified_orders"]+=cert["initial_ids"]
            counts["certified_answers"]+=cert["initial_scores"]
            counts["unique_order_not_certified"]+=len(ranks)==1 and not cert["initial_ids"]
            counts["unique_answer_not_certified"]+=len(answers)==1 and not cert["initial_scores"]
    write(HERE/"exhaustive-small.json",dict(counts),False);print(counts)

if __name__=="__main__":main()
