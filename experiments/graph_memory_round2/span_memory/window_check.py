import gzip, json, numpy as np
from run import D, E, read, save, e, rows, stream, sx
def main():
    names=["recent_center","recent_forward","point_center","point_forward"]
    weights=e.read("model.json")["flat"];m={}
    with gzip.open(D/"window_predictions.jsonl.gz","wt",encoding="utf8") as out:
        for k in range(8):
            for obj in rows(D/f"fresh_{k}.jsonl.gz"):
                i=obj["instance"]
                for t,rr,idx,meta,hist,last in stream(obj):
                    choices={a:idx[:3] for a in names}
                    if len(idx)>3:
                        F,_,_=sx(rr,idx,meta,hist,last,t,obj)
                        z=sum(np.take(w,F[:,c]) for c,w in enumerate(weights))
                        porder=[idx[j] for j in np.argsort(-z,kind="stable")]
                        after={(rr[j][0],rr[j][1]):j for j in idx}
                        before={(rr[j][0],rr[j][2]):j for j in idx}
                        for a in names:
                            rank=idx if a.startswith("recent") else porder
                            center=rank[0];p,lo,hi,*_=rr[center]
                            forward=after.get((p,hi+1));left=before.get((p,lo-1))
                            c=[center]
                            if a.endswith("center") and left is not None:c.append(left)
                            if forward is not None:
                                c.append(forward)
                                if a.endswith("forward"):
                                    nxt=after.get((p,rr[forward][2]+1))
                                    if nxt is not None:c.append(nxt)
                            choices[a]=(c+[j for j in rank if j not in c])[:3]
                    e.packed(out,[i,t,choices])
    save("window_lock.json",{p.name:e.sha(p.read_bytes()) for p in [D/"WINDOW_PROTOCOL.md",D/"window_check.py",D/"window_predictions.jsonl.gz"]})
    for i,t,c in rows(D/"window_predictions.jsonl.gz"):m[i,t]=c
    outcomes=[]
    for i,t,span,oracle,main,cost in rows(D/"scored.jsonl.gz"):
        c=m[i,t];outcomes.append((i.split(".")[0],main["typed"],[int(bool(span) and set(span)<=set(c[a])) for a in names]))
    groups=sorted({r[0] for r in outcomes});res={}
    for j,a in enumerate(names):
        d=np.array([y-v[j] for q,y,v in outcomes])
        g=np.array([[d[[i for i,r in enumerate(outcomes) if r[0]==q]].sum(),sum(r[0]==q for r in outcomes)] for q in groups]);rs=np.random.default_rng(261118).integers(len(g),size=(10000,len(g)));bo=g[rs].sum(axis=1)
        res[a]={"hits":sum(v[j] for q,y,v in outcomes),"wins":int((d==1).sum()),"losses":int((d==-1).sum()),"ci":np.quantile(bo[:,0]/bo[:,1],[.025,.975]).tolist()}
    save("window_results.json",dict(n=len(outcomes),cuts=len(m),typed=sum(r[1] for r in outcomes),baselines=res))
if __name__=="__main__":main()
