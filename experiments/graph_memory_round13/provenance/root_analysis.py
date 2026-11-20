import statistics
from collections import Counter,defaultdict
import numpy as np
from common13 import D,read,dump,sha
from grade13 import distribution
def main():
    rows=read(D/'features.json.gz');direct=read(D/'direct_receipts.json');y=np.array([direct[r['id']]['hit'] for r in rows],bool);n=len(y);ids=np.array([r['iid'] for r in rows])
    named=np.array([r['root']!='/testbed' for r in rows]);pos=np.array([not r['trust']['prefix_red_flag'] for r in rows]);fresh=np.array([r['trust']['fresh_content'] for r in rows])
    boot=np.random.default_rng(13027).integers(0,len(set(ids)),(10000,len(set(ids))))
    masks=dict(named=named,named_no_prior_positive=named&~pos,named_fresh=named&fresh,named_fresh_no_prior_positive=named&fresh&~pos,all=~(named&~named))
    table={}
    for a,take in masks.items():
        res=distribution(y,take,ids,boot,13027)
        refcat={}
        for i,r in enumerate(rows):refcat.setdefault((ids[i],bool(named[i])),[]).append(i)
        expected=sum(int(take[vs].sum())*float(y[vs].mean()) for vs in refcat.values())
        res['within_issue_and_alias_expected_errors']=expected;table[a]=res
    rank=sorted(range(n),key=lambda i:(not bool(named[i]),sha(rows[i]['id'].encode())));m={}
    for frac in [.1,.25,.5,.75,.9,1]:
        k=round(frac*n);m[str(frac)]={'reused':k,'unsafe_reused':int(y[rank[:k]].sum())}
    grouped={}
    for nm,take in [('named',named),('generic',~named)]:
        grouped[nm]=dict(n=int(take.sum()),unsafe=int(y[take].sum()),tasks=len(set(ids[take])),repos=len(set(r['repo'] for r,a in zip(rows,take) if a)))
    overlap=dict(unsafe_generic_only=int((y&~named&~pos).sum()),unsafe_veto_only=int((y&named&pos).sum()),unsafe_both=int((y&~named&pos).sum()),unsafe_neither=int((y&named&~pos).sum()))
    dump(D/'alias_sensitivity.json',dict(groups=grouped,policies=table,alias_rank=m,unsafe_flags=overlap,alias_aurc=float(np.mean(np.cumsum(y[rank])/np.arange(1,n+1)))))
if __name__=='__main__':main()