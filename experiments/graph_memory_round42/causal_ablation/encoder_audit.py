from collections import Counter
from core42 import D,SEEDS,read,save,sha,firstfit
import numpy as np


def main():
    stats=Counter();gap=0.
    for sh in range(8):
        r=D/f"test-{sh}.json.gz";p=D/f"test-{sh}.npz"
        assert [sha(r),sha(p)]==read(D/f"features-{sh}-seal.json")["rows"]["test"]
        rows=read(r)
        with np.load(p) as a:
            cost=np.rint(np.expm1(a["meta"][:,1])).astype(int)
            for seed in SEEDS:
                semi=a[f"sem{seed}"]
                pos=0
                for q,t,n,ids in rows:
                    sl=slice(pos,pos+n);pos+=n
                    native=np.argsort(semi[sl,0]);actual=np.argsort(-semi[sl,3],kind="stable")
                    similarity=semi[sl,3]
                    # Largest CPU score separation of any inverted pair in the published order.
                    values=similarity[native]
                    if n>1:gap=max(gap,float(np.max(values[1:]-np.minimum.accumulate(values)[:-1])))
                    p1,p2=firstfit(native,cost[sl]),firstfit(actual,cost[sl])
                    stats.update(orders=1,identical=int(np.array_equal(native,actual)),top1=int(native[0]==actual[0]),
                                 firstfit_set=int(set(p1)==set(p2)),firstfit_list=int(p1==p2))
    save(D/"encoder-audit.json",dict(counts=stats,largest_inverted_dot_gap=gap,code=sha(D/"encoder_audit.py")))
    print(stats,"largest inverted similarity gap",gap)


if __name__=="__main__":main()
