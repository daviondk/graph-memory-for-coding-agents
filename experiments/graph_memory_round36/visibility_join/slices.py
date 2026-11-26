"""Descriptive, fixed output-size bins; observed workloads may differ in other ways."""
from common import *
import numpy as np
from statistics import median
def main():
    inp=load(D/"input.json.gz");d=load(D/"operator-timings.json.gz");tim={(h,c,m,k):median(v)/1000 for h,c,m,k,v in d["raw"]};res={}
    for name,lo,hi in (("0",0,1),("1_31",1,32),("32_127",32,128),("128_plus",128,float("inf"))):
        selected=[(int(h),r["cut"]) for h,z in inp.items() if int(h)<128 for r in z["checks"] if lo<=r["count"]<hi]
        stats={};hs=sorted({h for h,c in selected});ids={h:i for i,h in enumerate(hs)};rng=np.random.default_rng(363501);ii=rng.integers(0,len(hs),(10000,len(hs)))
        for m in ("flat","flat_stats","group_stats","group_fixed","group_arity"):
            stats[m]={}
            for k in ("pairs","degrees"):
                a=[tim[h,c,m,k] for h,c in selected];b=[tim[h,c,"flat",k] for h,c in selected];labs=[ids[h] for h,c in selected];aa=np.bincount(labs,weights=a);bb=np.bincount(labs,weights=b);ratio=aa[ii].sum(axis=1)/bb[ii].sum(axis=1)
                stats[m][k]=[float(np.mean(a)),float(np.sum(a)/np.sum(b)),np.quantile(ratio,[.025,.975]).tolist()]
        res[name]={"cuts":len(selected),"histories":len(hs),"read_us_ratio_ci":stats}
    save(D/"size-strata.json",res);print([(k,v["cuts"],v["histories"],v["read_us_ratio_ci"]["group_arity"]["degrees"]) for k,v in res.items()])
if __name__=="__main__":main()
