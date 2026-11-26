"""Post-outcome sensitivity, distinct from the ten sealed confirmatory choices."""
import re
import unicodedata
from grade import D, read, save, sha, canonical
import numpy as np
def tok(s):return re.findall(r"[^\W_]+",unicodedata.normalize("NFKC",s).lower())
def surface(q,title):
    words=tok(q);t=tok(title);blocked=set()
    for i in range(len(words)-len(t)+1):
        if t and words[i:i+len(t)]==t:blocked.update(range(i,i+len(t)))
    free=[w for i,w in enumerate(words) if i not in blocked]
    conj=any(w in ("and","or") for w in free)
    sa="same" in free and "as" in free[free.index("same")+1:]
    return conj,sa
def main(write=False):
    pre=read(D/"prediction-seal.json");pred=read(D/"predictions.json.gz");names=read(D/"chosen-titles.json.gz")
    questions=read(D/"questions.json.gz");gold=read(D/"gold.json.gz");ids=sorted(pred);cols=("primary_href","coord_cautious","learned_dev","surface_same_as")
    jf,ar=pre["arms"].index("href_first"),pre["arms"];output={};full=[];recs=[];seeds=[]
    for q in ids:
        r=pred[q];t=names[str(r["seed"])][1];c,s=surface(questions[q],t)
        assert c==r["coordination"];addr=r["direct_gate"][0]
        j=addr if addr>=0 and (c or s) else r["choices"][jf]
        g=set(gold[q][1]);p=[r["choices"][ar.index(k)] for k in cols[:-1]]+[j]
        hits=[len({canonical(t),canonical(names[str(i)][1])}&g) for i in p]
        output[q]=[j,c,s];full.append([int(h==len(g)) for h in hits]);recs.append([h/len(g) for h in hits]);seeds.append(r["seed"])
    f=np.asarray(full);rr=np.asarray(recs);_,gi=np.unique(seeds,return_inverse=True);g=int(gi.max()+1);sizes=np.bincount(gi)
    pairs=[(0,3),(3,1),(3,2)]
    differences=np.column_stack([x[:,a]-x[:,b] for a,b in pairs for x in (f,rr)])
    by=np.array([np.bincount(gi,weights=c,minlength=g) for c in differences.T]).T
    rng=np.random.default_rng(520117);boot=np.empty((10000,differences.shape[1]))
    for i in range(0,10000,100):
        idx=rng.integers(0,g,size=(100,g));boot[i:i+100]=by[idx].sum(axis=1)/sizes[idx].sum(axis=1)[:,None]
    lo,hi=np.quantile(boot,[.025,.975],axis=0);comp={}
    for j,(a,b) in enumerate(pairs):
        key=cols[a]+"-"+cols[b];comp[key]={}
        for k,metric in enumerate(("full","recall")):
            col=2*j+k;d=differences[:,col];comp[key][metric]=dict(delta_pp=float(d.mean()*100),ci95_pp=[float(lo[col]*100),float(hi[col]*100)],wins=int((d>0).sum()),losses=int((d<0).sum()))
    res=dict(phase="Exploratory after reading outcomes on this panel; rule fixed in the separate 2Wiki study.",
             original_results=sha(D/"results.json"),original_seal=sha(D/"prediction-seal.json"),arms=list(cols),full=dict(zip(cols,map(int,f.sum(axis=0)))),
             recall=dict(zip(cols,map(float,rr.mean(axis=0)))),additional_signal=sum(s and not c for j,c,s in output.values()),
             new_selections=sum(output[q][0]!=pred[q]["choices"][ar.index("coord_cautious")] for q in ids),contrasts=comp)
    if write:
        save(D/"surface-decisions.json.gz",output);save(D/"surface-results.json",res)
    else:assert read(D/"surface-decisions.json.gz")==output and read(D/"surface-results.json")==res
    return res
if __name__=="__main__":
    import sys
    print(main("--write" in sys.argv))
