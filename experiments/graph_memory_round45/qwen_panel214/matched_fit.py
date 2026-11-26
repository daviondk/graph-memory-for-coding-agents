"""Freeze low-dimensional three-field and expanded-field lexical controls before held-out scoring."""
from common import *
from collections import Counter
from functools import lru_cache
from scipy.stats import rankdata
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from fractions import Fraction
sys.path.insert(0,str(WORK/"graph_memory_round39/set_reader"))
from data import sets_native,labels
PRIVATE=CACHE/"runs-r40-lexical-native-input"
FILE="matched-tokens.json.gz"
def inputs():
    seal=read(OUT/"matched-token-seal.json");p=OUT/FILE;q=PRIVATE/FILE
    if p.exists():
        assert sha(p)==seal["forecasts_input"];PRIVATE.mkdir(exist_ok=True)
        if q.exists():assert sha(q)==sha(p)
        p.replace(q)
    assert sha(q)==seal["forecasts_input"]
    return read(q)
def rank_ids(scores,ids,seen=None):
    return [ids[i] for i in sorted(range(len(ids)),key=lambda i:((seen[i] if seen is not None else 0),-scores[i],ids[i]))[:8]]
def features(docs,q):
    n=len(docs);D=[Counter(v) for v in docs];lens=[len(v) for v in docs];avg=sum(lens)/n;df=Counter()
    for d in D:df.update(d.keys())
    qd=Counter(q);idf={v:np.log1p((n-c+.5)/(c+.5)) for v,c in df.items()}
    uq=set(qd);qw=sum(idf.get(v,np.log1p((n+.5)/.5)) for v in uq);qnorm=sum((c*idf.get(v,np.log1p((n+.5)/.5)))**2 for v,c in qd.items())**.5
    q2=set(zip(q,q[1:]));q3=set(zip(q,q[1:],q[2:]));rows=[]
    for tokens,d,l in zip(docs,D,lens):
        members=uq & d.keys()
        bm=sum(idf[t]*d[t]*2.2/(d[t]+1.2*(.25+.75*l/avg))*qd[t] for t in members)
        docnorm=sum((v*idf[t])**2 for t,v in d.items())**.5
        co=sum(qd[t]*d[t]*idf[t]**2 for t in members)/max(qnorm*docnorm,1e-12)
        rows.append([bm,co,len(members)/max(1,len(uq)),len(members)/max(1,len(d)),sum(idf[t] for t in members)/max(1e-12,qw),
             len(q2.intersection(zip(tokens,tokens[1:])))/max(1,len(q2)),len(q3.intersection(zip(tokens,tokens[1:],tokens[2:])))/max(1,len(q3)),l])
    base=np.asarray(rows,float);order=np.stack([rankdata(-base[:,i],method="average")/n for i in range(7)],axis=1)
    return np.hstack([base,order])
def complete(group,ids):
    chosen=set(ids);groups=group["required_evidence_groups"]
    return int(all(len(chosen.intersection(g["acceptable_evidence_ids"]))>=g.get("minimum_required",1) for g in groups) or
              any(set(alt)<=chosen for alt in group["alternative_minimal_sets"]))
def main():
    start=time.perf_counter();input_data=inputs();states=input_data["states"];tok=input_data["tokens"];source=read(R34/"features.json.gz");panel=read(OUT/"panel.json")
    train=sorted(q for q,r in source.items() if r["split"]=="train");dev=sorted(q for q,r in source.items() if r["split"]=="dev");test=panel["order"]
    assert len(train)==179 and len(dev)==101 and set(test).isdisjoint(set(train)|set(dev))
    gold=labels(set(train)|set(dev));y={};wt={};single=0
    for q in train:
        routes=sets_native(states[q]["ids"],gold[q]);positive=set()
        if routes:
            k=min(map(len,routes));positive=set().union(*(s for s in routes if len(s)==k))
        z=np.array([j in positive for j in range(len(states[q]["ids"]))],int);y[q]=z
        w=np.where(z,1/(2*max(1,z.sum())),1/(2*max(1,len(z)-z.sum())))
        if np.unique(z).size==1:w[:]=1/len(w);single+=1
        wt[q]=w
    result={q:{} for q in test};selection={};weights={};d={}
    for variant in ("three","nine"):
        f={}
        for q,v in states.items():
            docs=[tok[k][1] for k in v["doc"]];f[q]=features(docs,tok[v[variant]][1])
        x=np.concatenate([f[q] for q in train]);yy=np.concatenate([y[q] for q in train]);weight=np.concatenate([wt[q] for q in train])
        scaler=StandardScaler().fit(x,sample_weight=weight);X=scaler.transform(x)
        transformed={q:scaler.transform(f[q]) for q in [*dev,*test]};models={};val={}
        for c in (.1,1.,10.):
            model=LogisticRegression(C=c,max_iter=1000,solver="lbfgs",random_state=4021406).fit(X,yy,sample_weight=weight);models[c]=model
            val[c]=sum(complete(gold[q],rank_ids(model.decision_function(transformed[q]),states[q]["ids"])[:5]) for q in dev)
        chosen=min(val,key=lambda k:(-val[k],k));model=models[chosen];selection[variant]=dict(C=chosen,dev_hits=val)
        weights[variant]=dict(C=chosen,coef=model.coef_[0].tolist(),intercept=model.intercept_.tolist(),mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist())
        for q in test:
            v=states[q]
            for t,a in (("bm",f[q][:,0]),("lr",model.decision_function(transformed[q]))):
                name=t+variant
                result[q][name]=rank_ids(a,v["ids"]);result[q][name+"_seen"]=rank_ids(a,v["ids"],v["seen"])
    for name,qs in (("train",train),("dev",dev),("all214",test),("outside204",panel["remaining"])):
        d[name]=sum(tok[states[q]["three"]][1]!=tok[states[q]["nine"]][1] for q in qs)
    save("matched-predictions.json.gz",result);save("matched-weights.json",weights)
    save("matched-seal.json",dict(input=sha(OUT/"matched-token-seal.json"),protocol=sha(OUT/"MATCHED_INPUT_RU.md"),code=sha(OUT/"matched_fit.py"),selection=selection,
         train=len(train),dev=len(dev),single_class_train=single,forecasts=sha(OUT/"matched-predictions.json.gz"),weights=sha(OUT/"matched-weights.json"),different_queries=d,
         seconds=time.perf_counter()-start))
    print("Fit and froze matched controls on",len(test),"states. Dev choices",selection,"changed query counts",d)
if __name__=="__main__":main()
