import math,statistics
import numpy as np
from paths_a import *

def fit(records):
    data=sorted((g,d) for q,g,d in records if g is not None);n=len(records)
    opts=[(None,0,0.)];groups={}
    for g,d in data:groups.setdefault(g,[]).append(d)
    switched=0;total=0.
    for g,lst in groups.items():
        switched+=len(lst);total+=math.fsum(lst);opts.append((g,switched,total/n))
    best=max(o[2] for o in opts);winner=min((o for o in opts if o[2]>=best-1e-12),key=lambda o:(o[1],-1 if o[0] is None else o[0]))
    return winner,opts

def main():
    check();f=get(SEM/"manifest.json")["files"]
    for name in ("orders.json.gz","outcomes.json.gz"):assert sha(SEM/name)==f[name]
    orders=get(SEM/"orders.json.gz");outcomes=get(SEM/"outcomes.json.gz");records=[];folds={}
    for q,r in orders.items():
        a,b=r["dense"],r["linked_dense"];g=None if a==b else r["scores"][str(a)]-r["scores"][str(b)]
        assert g is None or g>=0
        d=outcomes[q]["arms"]["linked_dense"][1]-outcomes[q]["arms"]["dense"][1];records.append((q,g,d))
        folds[q]=int(hexb(("r50-adaptive-fold|"+outcomes[q]["cluster"]).encode()),16)%5
    best,opts=fit(records);positive=[v for q,v,d in records if v is not None and v>0];qt=float(np.quantile(positive,.25))
    cv=[];scored=[]
    for i in range(5):
        chosen,_=fit([r for r in records if folds[r[0]]!=i]);part=[r for r in records if folds[r[0]]==i];switch=[]
        for q,g,d in part:
            use=chosen[0] is not None and g is not None and g<=chosen[0];scored.append(d if use else 0);switch.append([q,int(use),d if use else 0.])
        cv.append(dict(fold=i,n=len(part),threshold=chosen[0],switched=sum(z[1] for z in switch),pp=100*statistics.mean(z[2] for z in switch),rows=switch))
    put(D/"threshold-trace.json.gz",dict(candidates=opts,cv=cv,records=records))
    put(D/"threshold-seal.json",dict(primary=best[0],train_switches=best[1],train_gain_pp=100*best[2],quarter=qt,
        positive=len(positive),cv_pp=100*statistics.mean(scored),trace=sha(D/"threshold-trace.json.gz"),registration=sha(D/"registration.json"),code=sha(Path(__file__))))
    print("frozen threshold",best,"quarter",qt,"CV",100*statistics.mean(scored),flush=True)
if __name__=="__main__":main()
