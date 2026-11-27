"""Restore zero-window issues in the predeclared resampling population."""
from collections import Counter
import numpy as np
from replay import HERE,PAST,PRIMARY,load,save

def stats(rows,roster,a,b):
    issue_ids=sorted({tr["issue"] for tr in roster})
    summ={q:[0,0] for q in issue_ids}
    for row in rows:
        summ[row["issue"]][0]+=row["score"][a][0]-row["score"][b][0]
        summ[row["issue"]][1]+=row["bytes"]
    v=np.array(list(summ.values()));n=len(v)
    weights=np.random.default_rng(58017).multinomial(n,[1/n]*n,size=20000)
    num,den=(weights@v).T;boot=100*num[den>0]/den[den>0]
    return dict(issues=n,no_windows=[q for q,(u,d) in summ.items() if not d],delta_bytes=int(v[:,0].sum()),
                pp=float(100*v[:,0].sum()/v[:,1].sum()),ci=np.quantile(boot,[.025,.975]).tolist(),
                win=int((v[:,0]>0).sum()),tie=int((v[:,0]==0).sum()),loss=int((v[:,0]<0).sum()))

def main():
    roster=load(PAST/"prefixes.json.gz");main=load(HERE/"windows.json.gz");extra=load(HERE/"compact-windows.json.gz")
    cases=(("primary",main,*PRIMARY),("compact",extra,"16384_all","16384_none"),
           ("cross_file",extra,"16384_all","16384_file"),
           ("fixed_cross_file",extra,"fixed_all","fixed_file"))
    out={}
    for name,rows,a,b in cases:
        total=stats(rows,roster,a,b)
        for field in ("actor","repo"):
            total[field]={s:stats([r for r in rows if r[field]==s],[t for t in roster if t[field]==s],a,b)
                         for s in {t[field] for t in roster}}
        folds=load(HERE/"results.json")["folds"]
        total["fixed_folds"]=[stats([r for r in rows if r["repo"] in f["repos"]],
                                    [t for t in roster if t["repo"] in f["repos"]],a,b) for f in folds]
        out[name]=total
        print(name,{k:total[k] for k in ("issues","no_windows","delta_bytes","pp","ci","win","tie","loss")})
    save(HERE/"cohort-results.json",out,False)
if __name__=="__main__":main()
