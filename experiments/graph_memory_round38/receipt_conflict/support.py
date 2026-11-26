"""Exploratory corroboration rules; freeze distances first, assess later."""
from collections import Counter,defaultdict
from predict import D,VIS,load,put,sha
import numpy as np,sys
RULES={"side":None,"near32":32,"near8":8,"near2":2}
def forecast():
    source=load(D/"predictions.json.gz")
    risk={}
    for q,r in source.items():
        confirmed={s:[i for i,flag in w if flag] for s,w in r["witness"].items()}
        distances={n:min((abs(n-i) for i in confirmed[s]),default=None) for n,_,s in r["old"]}
        assert all(d is None or d>0 for d in distances.values())
        risk[q]=distances
    put("support-distance.json.gz",risk)
    put("support-seal.json",dict(dist=sha((D/"support-distance.json.gz").read_bytes()),code=sha((D/"support.py").read_bytes()),
                               parent=sha((D/"seal.json").read_bytes()),protocol=sha((D/"PROTOCOL_SUPPORT_RU.md").read_bytes())))
def score():
    seal=load(D/"support-seal.json")
    assert seal["dist"]==sha((D/"support-distance.json.gz").read_bytes()) and seal["code"]==sha((D/"support.py").read_bytes())
    dist=load(D/"support-distance.json.gz");inputs=load(D/"predictions.json.gz");future=load(VIS/"observations.json.gz")
    output=[]
    for q,r in inputs.items():
        d={int(n):v for n,v in dist[q].items()};g=dict(future[q]["observed"]);old={n:s for n,s,_ in r["old"]}
        assert set(d)==set(old)
        correct={n for n,s in old.items() if g.get(n)==s}
        wrong={n for n,s in old.items() if n in g and g[n]!=s}
        bins=defaultdict(Counter);arms={}
        for n,v in d.items():
            key="no_witness" if v is None else "1_to_2" if v<=2 else "3_to_8" if v<=8 else "9_to_32" if v<=32 else "above_32"
            bins[key].update(slots=1,correct=int(n in correct),wrong=int(n in wrong))
        for k,limit in RULES.items():
            removed={n for n,v in d.items() if v is None or (limit is not None and v>limit)}
            w=len(removed)/len(d) if d else 0.
            arms[k]=[len(removed&correct),len(removed&wrong),len(removed),w*len(correct),w*len(wrong)]
        output.append(dict(q=q,zone=r["zone"],issue=r["issue"],visible=len(g),arms=arms,bins=bins))
    def aggregate(rows):
        issues=sorted({r["issue"] for r in rows});idx={s:i for i,s in enumerate(issues)}
        bins=defaultdict(Counter);arms={k:np.zeros((len(issues),5)) for k in RULES};den=np.zeros(len(issues))
        for r in rows:
            i=idx[r["issue"]];den[i]+=r["visible"]
            for k,v in r["arms"].items():arms[k][i]+=v
            for k,v in r["bins"].items():bins[k].update(v)
        rng=np.random.default_rng(38199);samp=rng.integers(len(issues),size=(10000,len(issues)));res={}
        for k,mat in arms.items():
            # Benefit direction here is retained fraction: positive = more correct or more errors.
            eq=(mat[:,3:5]-mat[:,:2])/den[:,None]
            de=-mat[:,:2]/den[:,None]
            res[k]=dict(totals=mat.sum(axis=0).tolist(),delta_vs_T=de.mean(0).tolist(),
                        delta_vs_T_ci95=np.quantile(de[samp].mean(1),[.025,.975],axis=0).tolist(),
                        delta_vs_equal_expectation=eq.mean(0).tolist(),equal_ci95=np.quantile(eq[samp].mean(1),[.025,.975],axis=0).tolist())
        return dict(issues=len(issues),episodes=len(rows),bins=bins,arms=res)
    groups={s:aggregate([r for r in output if r["zone"]==s]) for s in sorted({r["zone"] for r in output})}
    put("support-scored.json.gz",output)
    result=dict(total=aggregate(output),groups=groups,seal=sha((D/"support-seal.json").read_bytes()),
                scored=sha((D/"support-scored.json.gz").read_bytes()))
    put("support-results.json",result)
    for z,g in dict(all=result["total"],**groups).items():
        print(z,{k:v["totals"][:3] for k,v in g["arms"].items()})
if __name__=="__main__":
    {"forecast":forecast,"score":score}[sys.argv[1]]()

