"""Descriptive breakdown of pre-frozen allocations. No policy or parameter selection."""
from common5 import *
from collections import defaultdict
from conditional import np
def main():
    panel=defaultdict(lambda: defaultdict(lambda: np.zeros(4)))
    for r in rr(D/'budget_items.jsonl.gz'):
        if r['allowance']!=3:continue
        for a,k in r['depth'].items():
            for group in (r['panel'].rsplit('_',1)[-1],r['panel']):
                panel[group][a]+=np.array([1,r['gold_rank']<=k,k,r['bytes'][a]])
    result={}
    for g,arms in panel.items():
        result[g]={a:dict(n=int(x[0]),hits=int(x[1]),coverage=x[1]/x[0],mean_depth=x[2]/x[0],mean_bytes=x[3]/x[0]) for a,x in arms.items()}
    dump('budget_strata.json',result)
if __name__=='__main__':main()

