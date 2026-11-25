"""Score frozen allocations, treating reorderings as a sensitivity analysis."""
from collections import defaultdict
import numpy as np
from schedule import HERE,R29,NATIVE,BUDGET,read,write,checksum
from prepare import views,metrics
def main():
    seal=read(HERE/"decision-seal.json");assert checksum(HERE/"decisions.json.gz")==seal["decisions"]
    runs=read(HERE/"decisions.json.gz");native=read(NATIVE/"outcomes.json.gz");local=read(R29/"revision_reader/forecasts.json.gz")
    gold=views("edits");qs=sorted(native);groups=sorted({v["group"] for v in native.values()})
    index={q:i for i,q in enumerate(qs)}
    membership=np.array([[native[q]["group"]==g for q in qs] for g in groups],dtype=float)
    sizes=membership.sum(axis=1);draws=np.random.default_rng(30301).integers(len(groups),size=(10000,len(groups)))
    outcomes={"native":np.array([[native[q][m][0] for m in ("old","cold")] for q in qs]),
              "local_reader":np.array([[metrics(local[q][m]["text"],gold[q][1])[0] for m in ("old","new")] for q in qs])}
    cache=defaultdict(dict)
    for family,rep,model,mode,selected in runs:
        choice=np.zeros(len(qs),dtype=int);choice[[index[q] for q in selected]]=1
        assert choice.sum()==BUDGET
        cache[family,model,mode][rep]=100*outcomes[model][np.arange(len(qs)),choice]
    summary={}
    for family in ("shuffled","by_document"):
        summary[family]={}
        for model in outcomes:
            by={m:np.stack([v[i] for i in range(32)]) for (f,s,m),v in cache.items() if f==family and s==model}
            delta=by["dynamic_local"]-by["dynamic_basic"]
            per=delta.mean(axis=0);sums=membership@per
            bootstrap=sums[draws].sum(axis=1)/sizes[draws].sum(axis=1)
            summary[family][model]={"f1":{k:float(a.mean()) for k,a in by.items()},"local_minus_basic":{
                     "mean":float(delta.mean()),"conditional_ci95":np.quantile(bootstrap,[.025,.975]).tolist(),
                     "order_minmax":[float(delta.mean(axis=1).min()),float(delta.mean(axis=1).max())]}}
    write(HERE/"results.json",{"n":len(qs),"capacity":BUDGET,"clusters":len(groups),"simulations":len(runs),"modes":summary})
if __name__=="__main__":main()
