"""Enumerate all completions sharing an identical pair of suffix records."""
from itertools import product
from event_bounds import HERE,bounds
from run import save

def main():
    grouped_cases=pair_cases=0
    for universe in range(9):
        sets=[tuple(i for i in range(universe) if mask&(1<<i)) for mask in range(1<<universe)]
        for b in (1,2,3):
            groups={}
            for s in sets:
                groups.setdefault((s[-b:],len(s)),[]).append(sum(1<<i for i in s))
            for (sa,na),aa in groups.items():
                for (sb,nb),bb in groups.items():
                    possible=[(a&v).bit_count() for a in aa for v in bb]
                    lo,hi,c,z=bounds(sa,sb,na,nb)
                    assert set(possible)==set(range(lo,hi+1))
                    grouped_cases+=1
                    pair_cases+=len(possible)
    out=dict(universe_max=8,budgets=[1,2,3],pairs=pair_cases,distinct_record_pairs=grouped_cases,
             all_integer_cardinalities_attained=True)
    save(HERE/"sharpness.json",out)
    print(out)
if __name__=="__main__":main()
